from unittest import IsolatedAsyncioTestCase

# Contract definitions are now in the AdapterTest class

def EXPORT_FUNCTION(module):
    """
    Export function to filter and expose the module's public API
    """
    # Create a new module with only the public interface
    import types
    exported_module = types.ModuleType('run_exported')
    
    # Export the public functions
    if hasattr(module, 'application'):
        exported_module.application = module.application
    if hasattr(module, 'test'):
        exported_module.test = module.test
    if hasattr(module, 'resources'):
        exported_module.resources = module.resources
        
    return exported_module

class AdapterTest(IsolatedAsyncioTestCase):
    # Contract definitions at class level
    CONTRACT_DEFINITIONS = {
        'application': {
            'type': 'callable',
            'required': True
        },
        'test': {
            'type': 'callable',
            'required': False
        },
        'resources': {
            'type': 'dict',
            'required': False
        }
    }
    
    def __init__(self, *args,**kwargs):
        super(AdapterTest, self).__init__(*args, **kwargs)  # Chiamata al costruttore di unittest.TestCase
        #config = {'adapter':"api",'url':"https://api.github.com",'token': ""}
        #self.test = adapter(config=config)  # Inizializza il tuo adapter qui