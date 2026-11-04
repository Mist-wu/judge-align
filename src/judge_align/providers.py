"""Explicit providers; errors never include headers, API keys, or response bodies."""
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request


class ProviderError(RuntimeError):
    pass


def resolve_model(config):
    model = config.get("model") or os.environ.get(config.get("model_env", ""))
    if not model:
        raise ProviderError(f"Model is unset; set {config.get('model_env', 'model in config')}")
    return model


def post(url, body, headers, timeout=180):
    request = urllib.request.Request(url, data=json.dumps(body).encode(),
                                     headers={"Content-Type":"application/json", **headers})
    # A timed-out POST may already be billed. Retry only explicit HTTP retryable
    # responses here; ambiguous connection/timeouts are persisted by the runner.
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            code = exc.code
            if code in {429,500,502,503,504} and attempt < 2:
                time.sleep(2**(attempt+1))
                continue
            raise ProviderError(f"Provider HTTP {code}; response body withheld") from None
        except (urllib.error.URLError, TimeoutError):
            raise ProviderError("Provider transport error; billing outcome unknown") from None
    raise AssertionError("unreachable")


class APIProvider:
    def __init__(self, config):
        self.config = config
        self.model = resolve_model(config)
        self.key = os.environ.get(config["key_env"])
        if not self.key:
            raise ProviderError(f"Missing credential environment variable {config['key_env']}")

    def generate(self, messages):
        cfg = self.config
        if cfg["type"] == "openai-compatible":
            payload = {"model":self.model,"messages":messages,"temperature":0,
                       "max_tokens":cfg.get("max_output_tokens",1536),"response_format":{"type":"json_object"}}
            payload.update(cfg.get("request_options", {}))
            result = post(cfg["base_url"].rstrip("/")+"/chat/completions", payload,
                          {"Authorization":"Bearer "+self.key})
            text = result["choices"][0]["message"].get("content") or ""
            raw_usage = result.get("usage",{})
            usage = {"input_tokens":raw_usage.get("prompt_tokens"),"output_tokens":raw_usage.get("completion_tokens"),
                     "cached_input_tokens":raw_usage.get("prompt_cache_hit_tokens",0),"provider_usage":raw_usage}
            return text, usage, {"model":result.get("model",self.model),"finish_reason":result["choices"][0].get("finish_reason"),"max_output_tokens":payload["max_tokens"]}
        if cfg["type"] == "gemini":
            model = self.model.removeprefix("models/")
            url = cfg["base_url"].rstrip("/")+"/models/"+urllib.parse.quote(model,safe="")+":generateContent"
            payload = {"systemInstruction":{"parts":[{"text":messages[0]["content"]}]},
                "contents":[{"role":"user","parts":[{"text":messages[1]["content"]}]}],
                "generationConfig":{"temperature":0,"maxOutputTokens":cfg.get("max_output_tokens",1536),"responseMimeType":"application/json"}}
            if cfg.get('response_json_schema'):
                payload['generationConfig']['responseJsonSchema']=cfg['response_json_schema']
            result = post(url,payload,{"x-goog-api-key":self.key})
            candidates = result.get("candidates",[])
            if not candidates:
                raise ProviderError("Gemini returned no candidate (possibly safety filtered)")
            text = "".join(p.get("text","") for p in candidates[0].get("content",{}).get("parts",[]) if not p.get("thought"))
            if not text:
                raise ProviderError("Gemini returned no visible text")
            u=result.get("usageMetadata",{})
            usage={"input_tokens":u.get("promptTokenCount"),"output_tokens":u.get("candidatesTokenCount"),
                   "thought_tokens":u.get("thoughtsTokenCount",0),"cached_input_tokens":u.get("cachedContentTokenCount",0),"provider_usage":u}
            return text,usage,{"model":result.get("modelVersion",self.model),"finish_reason":candidates[0].get("finishReason"),
                               "max_output_tokens":payload['generationConfig']['maxOutputTokens'],
                               "structured_output":bool(cfg.get('response_json_schema'))}
        raise ProviderError("Unsupported API provider type")


class QwenProvider:
    def __init__(self, config):
        import torch
        from transformers import AutoTokenizer,AutoModelForCausalLM,BitsAndBytesConfig
        if not torch.cuda.is_available():
            raise ProviderError("Qwen execution requires CUDA; run on allocated Colab GPU, not agent-01")
        self.config=config
        self.model_name=resolve_model(config)
        self.tokenizer=AutoTokenizer.from_pretrained(self.model_name,revision=config.get("revision","main"))
        quantization=BitsAndBytesConfig(load_in_4bit=True,bnb_4bit_quant_type="nf4",bnb_4bit_use_double_quant=True,bnb_4bit_compute_dtype=torch.bfloat16)
        self.model=AutoModelForCausalLM.from_pretrained(self.model_name,revision=config.get("revision","main"),device_map="auto",torch_dtype=torch.bfloat16,quantization_config=quantization)
        self.model.eval()
        self.env={"torch":torch.__version__,"cuda":torch.version.cuda,"gpu":torch.cuda.get_device_name(),
                  "model_commit":getattr(self.model.config,"_commit_hash",None),"quantization":"bitsandbytes nf4 4-bit"}

    def generate(self,messages):
        import torch
        inputs=self.tokenizer.apply_chat_template(messages,tokenize=True,add_generation_prompt=True,return_tensors="pt",return_dict=True).to(self.model.device)
        length=inputs["input_ids"].shape[-1]
        maximum=self.config.get("max_input_tokens",8192)
        if length>maximum:
            raise ProviderError(f"Input has {length} tokens, exceeds configured {maximum}; no silent truncation")
        with torch.inference_mode():
            outputs=self.model.generate(**inputs,max_new_tokens=self.config.get("max_output_tokens",1536),do_sample=False,pad_token_id=self.tokenizer.eos_token_id)
        continuation=outputs[0,length:]
        return self.tokenizer.decode(continuation,skip_special_tokens=True),{"input_tokens":length,"output_tokens":len(continuation),"cached_input_tokens":0},{"model":self.model_name,**self.env}


def make_provider(config):
    return QwenProvider(config) if config["type"]=="transformers" else APIProvider(config)


def estimated_cost(usage,config):
    """Unknown pricing remains null, never misleadingly reported as free."""
    price=config.get("pricing_usd_per_million")
    if not price or usage.get("input_tokens") is None or usage.get("output_tokens") is None:
        return None
    cached=usage.get("cached_input_tokens",0) or 0
    output=usage["output_tokens"]+(usage.get("thought_tokens",0) or 0)
    return ((usage["input_tokens"]-cached)*price["input"]+cached*price.get("cached_input",price["input"])+output*price["output"])/1_000_000
