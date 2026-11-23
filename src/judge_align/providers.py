"""Explicit providers; errors never include headers, API keys, or response bodies."""
import http.client
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request


class ProviderError(RuntimeError):
    pass


class UnknownBillingError(ProviderError):
    """Transport or response-stream failure whose billing outcome is unknown."""
    pass


def resolve_model(config):
    model = config.get("model") or os.environ.get(config.get("model_env", ""))
    if not model:
        raise ProviderError(f"Model is unset; set {config.get('model_env', 'model in config')}")
    return model


def post(url, body, headers, timeout=180, retry_rejected=False):
    """POST JSON once unless the provider documents an unbilled rejection.

    Server errors and HTTP 408 may follow execution, so they stay unresolved.
    HTTP 429 is sent again only when retry_rejected is true. Connection and
    timeout failures stay unknown and are not sent again here.
    """
    request = urllib.request.Request(url, data=json.dumps(body).encode(),
                                     headers={"Content-Type":"application/json", **headers})
    tries = 3 if retry_rejected else 1
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            code = exc.code
            exc.close()
            if code == 429 and attempt + 1 < tries:
                time.sleep(2**(attempt+1))
                continue
            if 500 <= code < 600 or code == 408 or (code == 429 and not retry_rejected):
                raise UnknownBillingError(f"Provider HTTP {code}; billing outcome unknown") from None
            raise ProviderError(f"Provider HTTP {code}; response body withheld") from None
        except (urllib.error.URLError, TimeoutError, http.client.HTTPException, OSError):
            raise UnknownBillingError("Provider transport error; billing outcome unknown") from None
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise UnknownBillingError("Provider returned non-JSON HTTP response; billing outcome unknown") from None
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
                          {"Authorization":"Bearer "+self.key},
                          retry_rejected=cfg.get("retry_unbilled_rejection") is True)
            choices = result.get("choices") or []
            if not choices or not isinstance(choices[0], dict):
                raise ProviderError("OpenAI-compatible provider returned no choices")
            text = (choices[0].get("message") or {}).get("content") or ""
            raw_usage = result.get("usage",{})
            usage = {"input_tokens":raw_usage.get("prompt_tokens"),"output_tokens":raw_usage.get("completion_tokens"),
                     "cached_input_tokens":raw_usage.get("prompt_cache_hit_tokens",0),"provider_usage":raw_usage}
            return text, usage, {"model":result.get("model",self.model),"finish_reason":choices[0].get("finish_reason"),"max_output_tokens":payload["max_tokens"]}
        if cfg["type"] == "gemini":
            model = self.model.removeprefix("models/")
            url = cfg["base_url"].rstrip("/")+"/models/"+urllib.parse.quote(model,safe="")+":generateContent"
            payload = {"systemInstruction":{"parts":[{"text":messages[0]["content"]}]},
                "contents":[{"role":"user","parts":[{"text":messages[1]["content"]}]}],
                "generationConfig":{"temperature":0,"maxOutputTokens":cfg.get("max_output_tokens",1536),"responseMimeType":"application/json"}}
            if cfg.get('response_json_schema'):
                payload['generationConfig']['responseJsonSchema']=cfg['response_json_schema']
            result = post(url,payload,{"x-goog-api-key":self.key},
                          retry_rejected=cfg.get("retry_unbilled_rejection") is True)
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
            raise ProviderError("Qwen execution requires CUDA")
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

    def generate_batch(self,conversations):
        import torch
        self.tokenizer.padding_side='left'
        if self.tokenizer.pad_token_id is None:self.tokenizer.pad_token_id=self.tokenizer.eos_token_id
        inputs=self.tokenizer.apply_chat_template(conversations,tokenize=True,add_generation_prompt=True,
            padding=True,return_tensors='pt',return_dict=True).to(self.model.device)
        lengths=inputs['attention_mask'].sum(dim=1).tolist()
        if max(lengths)>self.config.get('max_input_tokens',8192):
            raise ProviderError('A batch input exceeds the frozen input capacity; no truncation was applied')
        width=inputs['input_ids'].shape[1]
        with torch.inference_mode():
            outputs=self.model.generate(**inputs,max_new_tokens=self.config.get('max_output_tokens',1536),
                do_sample=False,pad_token_id=self.tokenizer.eos_token_id)
        eos=self.model.generation_config.eos_token_id
        eos=set(eos if isinstance(eos,list) else [eos])
        result=[]
        for length,sequence in zip(lengths,outputs[:,width:].tolist()):
            end=next((i+1 for i,token in enumerate(sequence) if token in eos),len(sequence))
            tokens=sequence[:end]
            result.append((self.tokenizer.decode(tokens,skip_special_tokens=True),
                {'input_tokens':length,'output_tokens':len(tokens),'cached_input_tokens':0},
                {'model':self.model_name,**self.env,'batch_size':len(conversations),
                 'padding_side':'left','input_padding_excluded':True,'output_stopped_at_first_eos':True}))
        return result


def make_provider(config):
    return QwenProvider(config) if config["type"]=="transformers" else APIProvider(config)


def estimated_cost(usage,config):
    """Unknown pricing remains null, never misleadingly reported as free."""
    price=config.get("pricing_usd_per_million")
    if not price or usage.get("input_tokens") is None or usage.get("output_tokens") is None:
        return None
    cached=usage.get("cached_input_tokens",0) or 0
    if cached < 0 or cached > usage["input_tokens"]:
        return None
    output=usage["output_tokens"]+(usage.get("thought_tokens",0) or 0)
    return ((usage["input_tokens"]-cached)*price["input"]+cached*price.get("cached_input",price["input"])+output*price["output"])/1_000_000
