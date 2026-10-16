import json,logging
import uvicorn
from .config import Settings
from .api import create_app
if __name__=='__main__':
    settings=Settings();logging.basicConfig(level=logging.INFO,format='%(message)s')
    uvicorn.run(create_app(settings),host='0.0.0.0',port=settings.port,log_config=None,access_log=False,timeout_keep_alive=10)
