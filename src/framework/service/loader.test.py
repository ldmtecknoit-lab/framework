from unittest import IsolatedAsyncioTestCase

# Contract definitions are in the AdapterTest class

def EXPORT_FUNCTION(module):
    """
    Export function to filter and expose the module's public API
    """
    # Create a new module with only the public interface
    import types
    exported_module = types.ModuleType('loader_exported')
    
    # Export the public functions
    if hasattr(module, 'bootstrap'):
        exported_module.bootstrap = module.bootstrap
        
    return exported_module

class AdapterTest(IsolatedAsyncioTestCase):
    # Contract definitions at class level
    CONTRACT_DEFINITIONS = {
        'bootstrap': {
            'type': 'callable',
            'required': True
        }
    }
    
    def __init__(self, *args,**kwargs):
        super(AdapterTest, self).__init__(*args, **kwargs)  # Chiamata al costruttore di unittest.TestCase