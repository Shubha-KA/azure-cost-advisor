import sys, pathlib, traceback
sys.path.append(r'C:/Users/Admin/Desktop/azure-cost-advisor')
modules = [
    'src.collector.run',
    'src.processor.normalizer',
    'src.dashboard.app',
    'src.ai.advisor',
]
for m in modules:
    try:
        __import__(m)
        print('IMPORT OK', m)
    except Exception as e:
        print('IMPORT FAIL', m, e)
        traceback.print_exc()
