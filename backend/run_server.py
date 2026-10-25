import sys
sys.path.insert(0, '.')
import uvicorn
if __name__ == '__main__':
    # uvicorn requires an APPLICATION IMPORT STRING when reload=True; passing
    # the app object with reload enabled exits immediately (code 3).
    uvicorn.run('app.main:app', host='127.0.0.1', port=8000, reload=True)
