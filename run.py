"""Start the IBN system:  python run.py   then open http://localhost:5000"""
from ibn.interface.web import create_app

if __name__ == "__main__":
    # 127.0.0.1 = only this PC can open the page. Change to "0.0.0.0" to allow
    # other PCs, but only on a trusted lab network (there is no login yet).
    create_app().run(host="127.0.0.1", port=5000, debug=True)
