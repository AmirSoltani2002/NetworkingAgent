import logging
import uvicorn
from .api import create_app
logging.basicConfig(level=logging.INFO,format='%(levelname)s %(name)s %(message)s')
uvicorn.run(create_app(),host='0.0.0.0',port=8110,ws='websockets',access_log=False)
