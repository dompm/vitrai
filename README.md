# Vitraux

Prototype for a stained-glass planning web app: map real glass sheet photos onto pattern pieces (2D "UV mapping").

## Prerequisites
- `uv` (Python). You already have it installed.
- `mise` (toolchain manager for Node + pnpm). Installed locally at `~/.local/bin/mise`.

If you haven't yet, activate `mise` in your shell (zsh):

```bash
echo 'eval "$($HOME/.local/bin/mise activate zsh)"' >> ~/.zshrc
source ~/.zshrc
```

## Frontend (V1 prototype)

```bash
cd frontend
pnpm install
pnpm dev
```

Then open `http://localhost:5173/`.

V1 features:
- Loads `data/mountains_pattern.png` and `data/zeuogbi0g35b1.jpg` (copied into `frontend/public/assets/`)
- Shows two sample piece polygons
- Lets you select a piece and drag the glass texture within it
- Slider for scale and numeric input for rotation

## Backend (health endpoint)

```bash
cd backend
uv run uvicorn main:app --reload --port 8000
```

Then open `http://localhost:8000/health`.

## SAM2 inference on Modal

Deploy the SAM2 box-segmentation service:

```bash
cd modal
modal deploy sam2_app.py
```

Run the backend (it will call the deployed Modal function):

```bash
cd backend
export VITRAUX_MODAL_APP="vitraux-sam2"
uv run uvicorn main:app --reload --port 8000
```

