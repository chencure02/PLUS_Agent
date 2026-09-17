# Installation Guide

This guide targets local Windows usage. The app itself is Python-based and runs through Chainlit. The PLUS runtime is a local native dependency and should be placed in an ASCII-only path.

## Requirements

- Windows 10/11
- Anaconda or Miniconda
- Git
- A supported LLM API key, unless you only test the managed workflow branches that do not require a model call
- Official PLUS runtime files available locally

## Recommended Directory

Use an English/ASCII path:

```text
C:\GIS\PLUS_Agent
```

The PLUS backend may fail when paths contain Chinese characters or unsupported symbols.

## Install With Script

```powershell
git clone https://github.com/chencure02/PLUS_Agent.git
cd PLUS_Agent
.\setup.bat
conda activate plus-agent
```

If package downloads are slow, configure conda and pip mirrors before running the setup script.

## Manual Install

```powershell
conda create -n plus-agent python=3.11 -y
conda activate plus-agent
conda install -c conda-forge gdal -y
python -m pip install -r requirements.txt
```

## Configure Environment

```powershell
copy .env.example .env
```

The app supports these LLM backends:

- `claude`
- `openai`
- `deepseek`
- `qwen`

You can also enter the API key in the Chainlit settings panel after login. Keep `.env` private.

## Prepare PLUS Runtime

The public repository intentionally excludes native PLUS executables, DLLs, model files, temporary parameter files, and generated outputs.

Place the official runtime files in:

```text
plus-backend\cpp\
```

Expected runtime shape:

```text
plus-backend\
  convert.bat
  expansion.bat
  leas.bat
  markov.bat
  cars.bat
  validate.bat
  cpp\
    PLUS.exe
    required DLL files
```

## Start The App

```powershell
conda activate plus-agent
chainlit run agent/main.py --host 0.0.0.0 --port 8000
```

Then open:

```text
http://localhost:8000
```

Register a local account on first use. Accounts and chat history are stored in the local Chainlit database, which is ignored by Git.

## Verify

```powershell
python -m unittest discover -s tests -v
python -m compileall agent tests scripts
python scripts/check_release_readiness.py
```

## Troubleshooting

- If the model call fails, check the selected backend, API key, base URL, and network access from the terminal that launched Chainlit.
- If PLUS execution fails, confirm the project path is ASCII-only and the runtime files exist under `plus-backend\cpp\`.
- If the data panel is empty, make sure you are viewing the same Chainlit conversation where the files were uploaded or generated.
- If GeoScene preview fails, check browser network access to `https://js.geoscene.cn/4.32/`.
