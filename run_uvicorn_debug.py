import os
import sys
from pathlib import Path

# ensure package root is on sys.path
p = Path(__file__).parent
sys.path.insert(0, str(p))

os.environ.setdefault('OFFERLOOP_DEBUG', '1')

import uvicorn

if __name__ == '__main__':
    uvicorn.run('app.main:app', host='127.0.0.1', port=8000)
