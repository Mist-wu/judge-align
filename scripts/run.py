#!/usr/bin/env python3
"""CLI usable directly after worktree upload, without installation."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from judge_align.cli import main
raise SystemExit(main())
