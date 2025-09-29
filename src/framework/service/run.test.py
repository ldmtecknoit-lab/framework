from unittest import IsolatedAsyncioTestCase

class AdapterTest(IsolatedAsyncioTestCase):
    def __init__(self, *args,**kwargs):
        super(AdapterTest, self).__init__(*args, **kwargs)  # Chiamata al costruttore di unittest.TestCase
        #config = {'adapter':"api",'url':"https://api.github.com",'token': ""}
        #self.test = adapter(config=config)  # Inizializza il tuo adapter qui