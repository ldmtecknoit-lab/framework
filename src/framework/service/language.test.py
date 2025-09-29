import asyncio
import types
import inspect # NUOVO: Necessario per EXPORT_FUNCTION
from datetime import datetime, timezone # Necessario per le funzioni di trasformazione
from typing import Any, Union, Dict, Callable # Aggiunto per chiarezza
import unittest # Aggiunto per chiarezza, anche se eredita da test.test
import test 


resources = {
    'factory': 'framework/service/factory.py',
    'flow': 'framework/service/flow.py',
    'test': 'framework/service/test.py',
    'model': 'framework/schema/model.json',
}


# --- Funzioni di Trasformazione di Esempio per i Test ---
def format_price_eur(price):
    if price is None:
        return None
    return f"{price:.2f} EUR"

def convert_timestamp_to_date_str(ts_string):
    if ts_string is None:
        return None
    dt_obj = datetime.fromisoformat(ts_string.replace('Z', '+00:00'))
    return dt_obj.strftime("%Y-%m-%d")

def status_to_boolean(status_code):
    if status_code == 1:
        return True
    elif status_code == 0:
        return False
    return None

class Test(test.test):
    
    # === 1. OGGETTO DI DEFINIZIONE DEL CONTRATTO ===
    CONTRACT_DEFINITIONS = {
        'DEFAULT_LANG_CODE': 'it',
        # Lista dell'API pubblica attesa per language.py (usata in EXPORT_FUNCTION)
        'PUBLIC_API_NAMES': [
            'resource', 'model', 'get', 'put', 'translation', 'extract_params', 
            'route', 'route2', 'route3', 'last', 'get_confi', 'load_provider', 
            'load_manager', 'ResourceLoadError', 'MyCustomValidator',
            'backend', 'extract_modules_from_code', 'json_to_pydict', 
            'generate_identifier', 'time_now_utc', 'wildcard_match', 'convert'
        ],
        # In questo caso, le funzioni di trasformazione restano nel test, 
        # ma potresti volerle nel contratto se l'implementazione le usa.
    }

    schema = {
        'user': {
            'type': 'dict',
            'schema': {
                #'id': {'type': 'string', 'required': True},
                'name': {'type': 'string', 'required': True},
                'age': {'type': 'integer', 'min': 0},
                'address': {
                    'type': 'dict',
                    'schema': {
                        'street': {'type': 'string'},
                        'city': {'type': 'string'},
                        'zip': {'type': 'string', 'regex': r'^\d{5}$'} # Raw string per regex
                    }
                },
                'items': {
                    'type': 'list',
                    'schema': { # Schema per ogni elemento della lista
                        'type': 'dict',
                        'schema': {
                            'id': {'type': 'integer'},
                            'name': {'type': 'string'}
                        }
                    }
                }
            }
        },
        'config': {
            'type': 'dict',
            'schema': {
                'version': {'type': 'float'},
                'active': {'type': 'boolean'}
            }
        }
    }

    def setUp(self):
        print("Setting up the test environment...")

    async def test_resource(self):
        """Verifica che language.get recuperi correttamente i valori da percorsi validi."""
        success = [
            {'args':(language),'kwargs':{'path':"framework/service/run.py"},'type':types.ModuleType},
            {'args':(language),'kwargs':{'path':"framework/schema/model.json"},'equal':model},
        ]

        failure = [
            {'args':(language),'kwargs':{'path':"framework/service/NotFound.py"}, 'error': FileNotFoundError},
        ]

        await self.check_cases(language.resource, success)
        await self.check_cases(language.resource, failure)
    
    async def test_model(self):
        success = [
            #1 Recupera il modello
            {'args':(self.schema,{'user': {'name':'marco','items': [{'id': 123, 'name': 'Prodotto A'}]}}),'equal':{'user': {'name':'marco','items': [{'id': 123, 'name': 'Prodotto A'}]}}},
        ]

        failure = [
            #1 Campo mancante
            {'args':(self.schema,{'user': {'ok':'m','name':'marco','items': [{'id': 123, 'name': 'Prodotto A'}]}}),'error': ValueError},
        ]

        await self.check_cases(language.model, success)
        await self.check_cases(language.model, failure)

    async def test_put(self):
        
        # --- CASI DI SUCCESSO ---
        success_cases = [
            #1 Inserimento iniziale, crea 'user' come dict
            {'args': ({}, 'user.name', 'Alice', self.schema), 'equal': {'user': {'name': 'Alice'}}},
            #2 Crea 'address' come dict
            {'args': ({'user': {'name': 'Alice'}}, 'user.address.street', 'Via Roma', self.schema), 'equal': {'user': {'name': 'Alice', 'address': {'street': 'Via Roma'}}}},
            #3 Crea 'items' come lista e il primo elemento come dict
            {'args': ({'user': {'name': 'Alice'}}, 'user.items.0.id', 123, self.schema), 'equal': {'user': {'name': 'Alice', 'items': [{'id': 123}]}}},
            #4 Aggiunge nome al primo elemento della lista
            {'args': ({'user': {'items': [{'id': 123}]}}, 'user.items.0.name', 'Prodotto A', self.schema), 'equal': {'user': {'items': [{'id': 123, 'name': 'Prodotto A'}]}}},
            #5 Aggiorna un valore esistente
            {'args': ({'user': {'name': 'Bob'}}, 'user.name', 'Charlie', self.schema), 'equal': {'user': {'name': 'Charlie'}}},
        ]

        # --- CASI DI FALLIMENTO ---
        failure_cases = [
            #1 Campo non definito nello schema
            {'args': ({}, 'user.invalid_field', 'Value', self.schema), 'error': IndexError},
            #2 Tipo di nodo intermedio sbagliato 
            {'args': ({}, 'user.0.name', 'Alice', self.schema), 'error': IndexError},
            #3 Tipo non corrispondente allo schema (stringa per int)
            {'args': ({'user': {}}, 'user.age', '30', self.schema), 'error': ValueError},
            #4 Regex non corrispondente
            {'args': ({'user': {'address':{}}}, 'user.address.zip', 'ABCDE', self.schema), 'error': ValueError},
            #5 Tentativo di accedere con chiave stringa a una lista
            {'args': ({'user': {'items':[]}}, 'user.items.my_item.id', 1, self.schema), 'error': IndexError},
            #7 Dominio vuoto
            {'args': ({}, '', 'value', self.schema), 'error': ValueError},
        ]

        await self.check_cases(language.put, success_cases)
        await self.check_cases(language.put, failure_cases)


    async def test_extract_params(self):
        success = [
            {'args':("func(name: 'Alice', age: 30, city: 'New York')"),'equal':{'name': 'Alice', 'age': 30, 'city': 'New York'}},
            {'args':("process(id: 123, options: {'mode': 'fast', 'verbose': True})"),'equal':{'id': 123, 'options': {'mode': 'fast', 'verbose': True}}},
            {'args':("analyze(data: [1, 2, 3, {'x': 10}], threshold: 0.5)"),'equal':{'data': [1, 2, 3, {'x': 10}], 'threshold': 0.5}},
            {'args':("empty_func()"),'equal':{}},
            {'args':("some_action(status: None, debug: False)"),'equal':{'status': None, 'debug': False}},
        ]
        
        # Test che si aspetta che extract_params gestisca la sintassi JSON/Python non perfetta
        failure = [
             {'args':("problematic(key: 'value with , comma', another: {nested_key: 'value, inside'})"),'equal':{'key': 'value with , comma', 'another': {'nested_key': 'value, inside'}}},
             {'args':("simple(name: Bob)"),'equal':{}}, # Valore non quotato non stringa
        ]

        await self.check_cases(language.extract_params, success)
        await self.check_cases(language.extract_params, failure)

    async def test_get(self):
        """Verifica che language.get recuperi correttamente i valori da percorsi validi."""
        success = [
            {'args':({'name': 'test_name'}, 'name'),'equal':'test_name'},
            {'args':({'url': {'path': '/api', 'query': {'id': 123}}}, 'url.query.id'),'equal':123},
            {'args':({'data': [1, 2, 3]}, 'data.1'),'equal':2},
            {'args':({'data': [{'item': 'value'}]}, 'data.0.item'),'equal':'value'},
            {'args':({'empty_dict': {}}, 'empty_dict.non_existent', 'default_value'),'equal':'default_value'},
            {'args':({}, 'none_value', 'fallback'),'equal':'fallback'},
            {'args':(['ciao'], '0'),'equal':'ciao'},

        ]

        failure = [
            {'args':(123,'id'), 'error': TypeError},
        ]

        await self.check_cases(language.get, success)
        await self.check_cases(language.get, failure)

    async def test_translation(self):
        """Verifica la mappatura base dei nomi dei campi senza trasformazioni."""
        api = {'version': {'type': 'float'}, 'active': {'type': 'boolean'},'users': {'type': 'dict', 'schema': {'name': {'type': 'string'}, 'age': {'type': 'integer'}}}}

        mapper = {
            'config.version': {'API': 'version','GITHUB': 'v'},
            'config.active': {'API': 'active','GITHUB': 'active'},
            'user.name': {'API': 'users.name','GITHUB': 'name'},
            'user.age': {'API': 'users.age','GITHUB': 'age'}
        }
        
        values = {} 

        success_cases = [
            {'args': ({'version':1.1,'active':True}, mapper, values, api, self.schema), 'equal': {'config': {'version': 1.1,'active': True}}},
            {'args': ({'config': {'version': 1.1,'active': True}}, mapper, values, self.schema, api), 'equal': {'version':1.1,'active':True}},
            {'args': ({'users': {'name': 'marco','age': 18}}, mapper, values, api, self.schema), 'equal': {'user': {'name': 'marco','age': 18}}},
            {'args': ({'user': {'name': 'marco','age': 18}}, mapper, values, self.schema, api), 'equal': {'users': {'name': 'marco','age': 18}}},
        ]

        failure = [
            # Errori di tipo nei parametri (test che la funzione verifica gli argomenti)
            {'args': ("{'version':1.1,'active':True,'sss':'a'}", mapper, values, api, self.schema), 'error': TypeError},
            {'args': ({'version':1.1,'active':True}, [], values, api, self.schema), 'error': TypeError},
            {'args': ({'version':1.1,'active':True,'sss':'a'}, mapper, (1,2,3), api, self.schema), 'error': TypeError},
            {'args': ({'version':1.1,'active':True}, mapper, values, 'not_a_dict', self.schema), 'error': TypeError},
            {'args': ({'version':1.1,'active':True}, mapper, values, self.schema, 'not_a_dict'), 'error': TypeError},
            {'args': (), 'error': TypeError},
        ]

        await self.check_cases(language.translation, success_cases)
        await self.check_cases(language.translation, failure)


# === 2. FUNZIONE DI ESPORTAZIONE (IL FILTRO API) ===
def EXPORT_FUNCTION(full_module: types.ModuleType) -> types.ModuleType:
    """
    Riceve il modulo di implementazione language.py completamente eseguito 
    e restituisce un modulo filtrato che espone SOLO le funzioni e classi desiderate.
    """
    
    # Crea un nuovo modulo pulito per l'esportazione finale
    final_module = types.ModuleType(full_module.__name__)
    
    # Recupera l'elenco delle API pubbliche dal contratto definito nel file di test
    public_api_names = full_module.contract.get('PUBLIC_API_NAMES', [])
    
    # Copia solo gli attributi della lista 'public_api_names'
    for attr_name in public_api_names:
        if hasattr(full_module, attr_name):
            try:
                setattr(final_module, attr_name, getattr(full_module, attr_name))
            except AttributeError:
                # Ignora se l'attributo è in lista ma non è accessibile per qualche ragione
                pass

    # Aggiunge le definizioni del contratto al modulo finale per eventuale uso esterno
    final_module.contract = full_module.contract
    
    return final_module

'''import asyncio
import types

resources = {
    'factory': 'framework/service/factory.py',
    'flow': 'framework/service/flow.py',
    'test': 'framework/service/test.py',
    'model': 'framework/schema/model.json',
}


# --- Funzioni di Trasformazione di Esempio per i Test ---
def format_price_eur(price):
    if price is None:
        return None
    return f"{price:.2f} EUR"

def convert_timestamp_to_date_str(ts_string):
    if ts_string is None:
        return None
    dt_obj = datetime.fromisoformat(ts_string.replace('Z', '+00:00'))
    return dt_obj.strftime("%Y-%m-%d")

def status_to_boolean(status_code):
    if status_code == 1:
        return True
    elif status_code == 0:
        return False
    return None # O False, a seconda della logica desiderata

class Test(test.test):

    schema = {
        'user': {
            'type': 'dict',
            'schema': {
                #'id': {'type': 'string', 'required': True},
                'name': {'type': 'string', 'required': True},
                'age': {'type': 'integer', 'min': 0},
                'address': {
                    'type': 'dict',
                    'schema': {
                        'street': {'type': 'string'},
                        'city': {'type': 'string'},
                        'zip': {'type': 'string', 'regex': r'^\d{5}$'} # Raw string per regex
                    }
                },
                'items': {
                    'type': 'list',
                    'schema': { # Schema per ogni elemento della lista
                        'type': 'dict',
                        'schema': {
                            'id': {'type': 'integer'},
                            'name': {'type': 'string'}
                        }
                    }
                }
            }
        },
        'config': {
            'type': 'dict',
            'schema': {
                'version': {'type': 'float'},
                'active': {'type': 'boolean'}
            }
        }
    }

    def setUp(self):
        
        print("Setting up the test environment...")

    async def test_resource(self):
        """Verifica che language.get recuperi correttamente i valori da percorsi validi."""
        success = [
            {'args':(language),'kwargs':{'path':"framework/service/run.py"},'type':types.ModuleType},
            {'args':(language),'kwargs':{'path':"framework/schema/model.json"},'equal':model},
        ]

        failure = [
            {'args':(language),'kwargs':{'path':"framework/service/NotFound.py"}, 'error': FileNotFoundError},
        ]

        await self.check_cases(language.resource, success)
        await self.check_cases(language.resource, failure)
    
    async def test_model(self):
        success = [
            #1 Recupera il modello
            {'args':(self.schema,{'user': {'name':'marco','items': [{'id': 123, 'name': 'Prodotto A'}]}}),'equal':{'user': {'name':'marco','items': [{'id': 123, 'name': 'Prodotto A'}]}}},
        ]

        failure = [
            #1 Campo mancante
            {'args':(self.schema,{'user': {'ok':'m','name':'marco','items': [{'id': 123, 'name': 'Prodotto A'}]}}),'error': ValueError},
        ]

        await self.check_cases(language.model, success)
        await self.check_cases(language.model, failure)

    async def test_put(self):
        # Definisci il tuo schema Cerberus
        

        # --- CASI DI SUCCESSO ---
        # Gli args devono essere un tuple che contiene TUTTI gli argomenti per `put`
        success_cases = [
            #1 Inserimento iniziale, crea 'user' come dict
            {'args': ({}, 'user.name', 'Alice', self.schema), 'equal': {'user': {'name': 'Alice'}}},
            #2 Crea 'address' come dict
            {'args': ({'user': {'name': 'Alice'}}, 'user.address.street', 'Via Roma', self.schema), 'equal': {'user': {'name': 'Alice', 'address': {'street': 'Via Roma'}}}},
            #3 Crea 'items' come lista e il primo elemento come dict
            {'args': ({'user': {'name': 'Alice'}}, 'user.items.0.id', 123, self.schema), 'equal': {'user': {'name': 'Alice', 'items': [{'id': 123}]}}},
            #4 Aggiunge nome al primo elemento della lista
            {'args': ({'user': {'items': [{'id': 123}]}}, 'user.items.0.name', 'Prodotto A', self.schema), 'equal': {'user': {'items': [{'id': 123, 'name': 'Prodotto A'}]}}},
            #5 Aggiorna un valore esistente
            {'args': ({'user': {'name': 'Bob'}}, 'user.name', 'Charlie', self.schema), 'equal': {'user': {'name': 'Charlie'}}},
        ]

        # --- CASI DI FALLIMENTO ---
        failure_cases = [
            #1 Campo non definito nello schema
            {'args': ({}, 'user.invalid_field', 'Value', self.schema), 'error': IndexError},
            #2 Tipo di nodo intermedio sbagliato (tentativo di usare indice su dict quando lo schema attende stringa)
            {'args': ({}, 'user.0.name', 'Alice', self.schema), 'error': IndexError},
            #3 Tipo non corrispondente allo schema (stringa per int)
            {'args': ({'user': {}}, 'user.age', '30', self.schema), 'error': ValueError},
            #4 Regex non corrispondente
            {'args': ({'user': {'address':{}}}, 'user.address.zip', 'ABCDE', self.schema), 'error': ValueError},
            #5 Tentativo di accedere con chiave stringa a una lista (se lo schema attende una lista, ma viene data una stringa)
            {'args': ({'user': {'items':[]}}, 'user.items.my_item.id', 1, self.schema), 'error': IndexError},
            #6 Indice di lista negativo
            #{'args': ({'user': {'items':[]}}, 'user.items.-1.id', 1, my_schema), 'error': IndexError},
            #7 Dominio vuoto
            {'args': ({}, '', 'value', self.schema), 'error': ValueError},
        ]

        await self.check_cases(language.put, success_cases) # Passa la funzione put (non language.put)
        await self.check_cases(language.put, failure_cases) # Passa la funzione put


    async def test_extract_params(self):
        success = [
            {'args':("func(name: 'Alice', age: 30, city: 'New York')"),'equal':{'name': 'Alice', 'age': 30, 'city': 'New York'}},
            {'args':("process(id: 123, options: {'mode': 'fast', 'verbose': True})"),'equal':{'id': 123, 'options': {'mode': 'fast', 'verbose': True}}},
            {'args':("analyze(data: [1, 2, 3, {'x': 10}], threshold: 0.5)"),'equal':{'data': [1, 2, 3, {'x': 10}], 'threshold': 0.5}},
            {'args':("send(message: \"Hello, world!\", priority: 5)"),'equal':{'message': "Hello, world!", 'priority': 5}},
            {'args':("empty_func()"),'equal':{}}, # Funzione senza parametri
            {'args':("some_action(status: None, debug: False)"),'equal':{'status': None, 'debug': False}},
            {'args':("another_func(data: [1, 'two', 3], complex: {'a': [1,2], 'b': 'nested'})"),'equal':{'data': [1, 'two', 3], 'complex': {'a': [1, 2], 'b': 'nested'}}},
        ]

        failure_cases = [
            # Caso 1: Stringa JSON/Python malformata (es. virgole, apici mancanti)
            {'args':("bad_syntax(param: {'key': value)"), 'error': SyntaxError}, # Assumi che un parsing fallito dia SyntaxError o ValueError
            {'args':("incomplete(param: 'value'"), 'error': SyntaxError}, # Mancanza di chiusura parentesi
            {'args':("simple(name: Bob)"), 'error': ValueError}, # Valore non quotato che non è un tipo Python valido (int, float, bool, None)

            # Caso 2: Nomi di parametri invalidi
            # {'args':("invalid(0name: 'value')"), 'error': ValueError}, # Se la tua funzione convalida i nomi
            
            # Caso 3: Input non previsto per la funzione (es. non una stringa)
            {'args': (123,), 'error': TypeError}, # Se 'extract_params' si aspetta una stringa come input
            {'args': ({'a':1},), 'error': TypeError},
        ]

        failure = [
            {'args':("problematic(key: 'value with , comma', another: {nested_key: 'value, inside'})"),'equal':{'key': 'value with , comma', 'another': {'nested_key': 'value, inside'}}},
            {'args':("simple(name: Bob)"),'equal':{}}, # Chiave non quotata e valore non quotato non stringa   
        ]

        await self.check_cases(language.extract_params, success)
        await self.check_cases(language.extract_params, failure)

    async def test_get(self):
        """Verifica che language.get recuperi correttamente i valori da percorsi validi."""
        success = [
            {'args':({'name': 'test_name'}, 'name'),'equal':'test_name'},
            {'args':({'url': {'path': '/api'}}, 'url.path', ),'equal':'/api'},
            {'args':({'url': {'path': '/api', 'query': {'id': 123}}}, 'url.query.id'),'equal':123},
            {'args':({'data': [1, 2, 3]}, 'data.1'),'equal':2},
            {'args':({'data': [{'item': 'value'}]}, 'data.0.item'),'equal':'value'},
            {'args':({'nested': {'key': 'value'}}, 'nested.key'),'equal':'value'},
            {'args':({'list': [1, 2, 3]}, 'list.2'),'equal':3},
            {'args':({'mixed': {'a': 1, 'b': [10, 20]}}, 'mixed.b.1'),'equal':20},
            {'args':({'complex': {'a': {'b': 1}}}, 'complex.a.b'),'equal':1},
            {'args':({'empty_dict': {}}, 'empty_dict.non_existent', 'default_value'),'equal':'default_value'}, # Chiave inesistente con default
            {'args':({}, 'none_value', 'fallback'),'equal':'fallback'}, # Accesso a None con default
            {'args':({'list_data': [10, 20]}, 'list_data.0'),'equal':10}, # Accesso a lista con indice
            {'args':({'list_data': [{'item': 'val'}]}, 'list_data.0.item'),'equal':'val'}, # Accesso a lista di dizionari
            {'args':({}, 'a'),'equal':None}, # Verifica None esplicito come valore
            {'args':(['ciao'], '0'),'equal':'ciao'}, # Accesso a lista con indice

        ]

        failure = [
            {'args':(123,'id'), 'error': TypeError}, # Accesso a un intero, dovrebbe fallire
        ]

        await self.check_cases(language.get, success)
        await self.check_cases(language.get, failure)

    async def test_translation(self):
        """Verifica la mappatura base dei nomi dei campi senza trasformazioni."""
        api = {'version': {'type': 'float'}, 'active': {'type': 'boolean'},'users': {'type': 'dict', 'schema': {'name': {'type': 'string'}, 'age': {'type': 'integer'}}}}

        mapper = {
            'config.version': {'API': 'version','GITHUB': 'v'},
            'config.active': {'API': 'active','GITHUB': 'active'},
            'user.name': {'API': 'users.name','GITHUB': 'name'},
            'user.age': {'API': 'users.age','GITHUB': 'age'}
        }
        
        values = {} # Nessuna trasformazione dei valori

        success_cases = [
            {'args': ({'version':1.1,'active':True}, mapper, values, api, self.schema), 'equal': {'config': {'version': 1.1,'active': True}}},
            {'args': ({'config': {'version': 1.1,'active': True}}, mapper, values, self.schema, api), 'equal': {'version':1.1,'active':True}},
            {'args': ({'users': {'name': 'marco','age': 18}}, mapper, values, api, self.schema), 'equal': {'user': {'name': 'marco','age': 18}}},
            {'args': ({'user': {'name': 'marco','age': 18}}, mapper, values, self.schema, api), 'equal': {'users': {'name': 'marco','age': 18}}},
            #{'args': ({'version':1.1,'active':True}, self.schema, mapper, values, 'MODEL', 'API'), 'equal': {'config': {'version': 1.1,'active': True}}}
        ]

        failure = [
            #1 Errori di tipo nei parametri
            {'args': ("{'version':1.1,'active':True,'sss':'a'}", mapper, values, api, self.schema), 'error': TypeError},
            # 2 Mapper non è un dizionario
            {'args': ({'version':1.1,'active':True}, [], values, api, self.schema), 'error': TypeError},
            # 3 Valori non sono un dizionario
            {'args': ({'version':1.1,'active':True,'sss':'a'}, mapper, (1,2,3), api, self.schema), 'error': TypeError},
            # 4 Input non è un dizionario
            {'args': ({'version':1.1,'active':True}, mapper, values, 'not_a_dict', self.schema), 'error': TypeError},
            # 5 Output non è un dizionario
            {'args': ({'version':1.1,'active':True}, mapper, values, self.schema, 'not_a_dict'), 'error': TypeError},
            # 6 Mapper non è un dizionario
            {'args': ({'version':1.1,'active':True}, mapper, values, self.schema), 'error': TypeError},
            # 7 Valori non sono un dizionario
            {'args': (), 'error': TypeError},
            #{'args': ({'config': {'version': 1.1,'active': True}}, mapper, values, self.schema, api), 'error': ValueError},
            #{'args': ({'version':1.1,'active':True}, self.schema, mapper, values, 'MODEL', 'API'), 'equal': {'config': {'version': 1.1,'active': True}}}
        ]

        await self.check_cases(language.translation, success_cases)
        await self.check_cases(language.translation, failure)'''