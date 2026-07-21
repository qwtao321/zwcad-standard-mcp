from datetime import datetime

_logs=[]

def record(operation, permission, result):
    _logs.append({
        "time": datetime.now().isoformat(),
        "operation": operation,
        "permission": permission,
        "result": result
    })

def history():
    return _logs
