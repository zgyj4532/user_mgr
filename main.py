import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).parent))

from src.app.app import app

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
