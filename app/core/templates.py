import os
from pathlib import Path
from fastapi.templating import Jinja2Templates

# Get the base directory (project root)
BASE_DIR = Path(__file__).parent.parent.parent

# Initialize templates once
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))