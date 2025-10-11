import sys
import traceback
import os
import ast
import inspect
from typing import Dict, Any, Optional, List
import types
import json
import platform
import datetime
import logging
import psutil
import socket
import functools # Importato per il decoratore

# =====================================================================
# --- Configurazione Log e Formatter JSON (Invariata) ---
# =====================================================================

class JsonFormatter(logging.Formatter):
    def format(self, record):
        debug_report = getattr(record, 'debug_report', {}) 
        
        log_record = {
            'timestamp': self.formatTime(record, self.datefmt),
            'level': record.levelname,
            'message': record.getMessage(),
            'python_module': record.module,
            'line_number': record.lineno,
            'trace_id': debug_report.get('APPLICATION_CONTEXT', {}).get('REQUEST_ID', 'N/A'),
            'debug_report_data': debug_report
        }
        return json.dumps(log_record)

logger = logging.getLogger(__name__)
logger.setLevel(logging.ERROR)

if not logger.handlers:
    central_handler = logging.StreamHandler(sys.stderr) 
    central_handler.setFormatter(JsonFormatter(datefmt="%Y-%m-%d %H:%M:%S"))
    logger.addHandler(central_handler)

# =====================================================================
# --- Funzioni di Utilità (Helper) ---
# =====================================================================

def _get_system_info() -> Dict[str, Any]:
    """Raccoglie le informazioni chiave su CPU, RAM e Processo."""
    mem = psutil.virtual_memory()
    
    return {
        "hostname": socket.gethostname(),
        "process_id": os.getpid(),
        "cpu_cores_logical": psutil.cpu_count(),
        "cpu_cores_physical": psutil.cpu_count(logical=False),
        "ram_total_gb": round(mem.total / (1024**3), 2),
        "ram_available_gb": round(mem.available / (1024**3), 2),
        "os_name": platform.platform(),
    }

def _get_source_code_from_disk(filepath: str) -> Optional[str]:
    """Tenta di leggere un file sorgente dal disco."""
    if filepath.startswith('<') or not os.path.exists(filepath):
        return None
    try:
        if os.path.getsize(filepath) > 10 * 1024 * 1024:
            return None # Evita file troppo grandi
        with open(filepath, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return None

def _get_line_from_source(source_lines: List[str], lineno: int) -> str:
    """Recupera una specifica riga dal sorgente diviso."""
    index = lineno - 1
    if 0 <= index < len(source_lines):
        return source_lines[index].strip()
    return "RIGA SORGENTE NON TROVATA O FUORI LIMITE"

def sanitize_variable_value(name: str, value: Any) -> str:
    """Oscura variabili sensibili e tronca oggetti lunghi."""
    sensitive_keywords = ['password', 'secret', 'token', 'key', 'pwd', 'auth']
    
    if any(keyword in name.lower() for keyword in sensitive_keywords):
        return "******** [OSCURATO PER SICUREZZA]"
    
    try:
        repr_value = repr(value)
    except:
        return "<Unserializable Object>"
        
    MAX_LENGTH = 500
    if len(repr_value) > MAX_LENGTH:
        return f"{repr_value[:MAX_LENGTH]}... [TRONCATO, {len(repr_value)} caratteri]"
        
    return repr_value
    
def get_module_structure_from_string_fixed(source_code: str, module_name: str) -> Dict[str, Any]:
    """Analizza il codice sorgente (AST) per ricavare la struttura del modulo."""
    structure = {"module_name": module_name, "module_docstring": None}
    
    try:
        tree = ast.parse(source_code)
        if (ast.get_docstring(tree)):
            structure["module_docstring"] = ast.get_docstring(tree).strip()
            
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                func_info = {
                    "type": "function",
                    "data": {
                        "lineno": node.lineno,
                        "source_code_line": _get_line_from_source(source_code.splitlines(), node.lineno),
                        "docstring": ast.get_docstring(node),
                        "args": [a.arg for a in node.args.posonlyargs + node.args.args + [node.args.vararg] if a],
                    }
                }
                structure[node.name] = func_info

    except Exception as e:
        structure["parsing_error"] = f"Errore nell'analisi AST: {type(e).__name__} - {str(e)}"

    return structure

# =====================================================================
# --- FUNZIONE CRITICA AGGIORNATA: extract_detailed_traceback --- (FIXED)
# =====================================================================

# Sorgente del modulo iniettato usato nello scenario di test
# Questo è necessario per il FIX del codice dinamico
MODULE_CODE_RESOLVED = """
\"\"\"Modulo per la gestione delle richieste API in ambiente di produzione.\"\"\"

# Funzioni presenti nel modulo iniettato
def calculate_ratio(numerator, secret_key="1234"):
    # La variabile 'denominator' non è un argomento e non è definita qui.
    return numerator / denominator 

def run_test(user_id):
    value_a = 20.0
    value_b = 5.0
    
    return calculate_ratio(value_a + value_b, user_id)
"""

def extract_detailed_traceback(tb: Optional[types.TracebackType]) -> List[Dict[str, Any]]:
    """
    Estrae i frame del traceback in un formato strutturato, gestendo in modo robusto
    il recupero della riga di codice sorgente.
    """
    structured_tb = []
    current_tb = tb
    
    # Pre-carica il sorgente del modulo principale se è quello iniettato nello scenario di test
    in_memory_source_lines = MODULE_CODE_RESOLVED.splitlines()

    while current_tb is not None:
        frame = current_tb.tb_frame
        
        # Ignora le librerie di sistema
        filename = frame.f_code.co_filename
        if "/usr/" in filename or "/local/lib/python" in filename or "python3." in filename:
            current_tb = current_tb.tb_next
            continue

        # Estrai e sanifica le variabili locali del frame corrente
        local_vars_state = {
            k: sanitize_variable_value(k, v) 
            for k, v in frame.f_locals.items() 
            if not k.startswith('__') and k not in ['frame', 'frame_summary', 'current_tb', 'tb']
        }
        
        # === INIZIO FIX CRITICO PER Index/Source Error ===
        line_content = None
        
        # 1. Tentativo con traceback.FrameSummary (il più robusto per file su disco)
        try:
            # lookup_line=True forza la ricerca della riga dal disco/modulo
            frame_summary = traceback.FrameSummary(filename, frame.f_lineno, frame.f_code.co_name, lookup_line=True)
            if frame_summary.line:
                line_content = frame_summary.line.strip()
        except Exception:
            pass 

        # 2. Fallback per codice dinamico ('<string>' o nomi di file fittizi come 'api_handler_v1.py')
        if line_content is None and (filename.startswith('<') or filename.endswith('api_handler_v1.py')):
            try:
                # Usa il sorgente in memoria fornito dal blocco di test
                line_content = _get_line_from_source(in_memory_source_lines, frame.f_lineno)
            except Exception:
                pass

        # 3. Fallback finale
        if line_content is None:
            if filename.startswith('<'):
                line_content = "SORGENTE DINAMICA NON DISPONIBILE (exec/lambda)"
            else:
                line_content = "SORGENTE NON RECUPERATA DAL DISCO/MODULO"
        
        # === FINE FIX CRITICO ===

        structured_tb.append({
            "step_filename": filename,
            "step_lineno": frame.f_lineno,
            "step_function": frame.f_code.co_name,
            "step_code_line": line_content, 
            "local_variables_state": local_vars_state
        })
        current_tb = current_tb.tb_next
    
    return structured_tb

# =====================================================================
# --- DECORATORE PER GESTIONE ECCEZIONI (@capture_errors) ---
# =====================================================================

def capture_errors(custom_filename: str = "<code_in_memory>", app_context: Optional[Dict[str, Any]] = None):
    """
    Decoratore per catturare eccezioni, generare un rapporto di debug dettagliato
    e loggarlo usando il logger configurato.
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception:
                # Recupera il codice sorgente del modulo della funzione
                source_code = None
                try:
                    source_code = inspect.getsource(func)
                except (OSError, TypeError):
                    source_code = ""

                # Genera il rapporto usando l'eccezione attiva
                report = analyze_exception_with_module_structure(
                    source_code=source_code,
                    custom_filename=custom_filename,
                    app_context=app_context
                )
                
                exc_type, exc_value, _ = sys.exc_info()
                error_message = f"Errore intercettato in '{func.__name__}': {type(exc_value).__name__} - {str(exc_value)}"
                
                # Logga l'errore con il rapporto JSON
                logger.error(
                    error_message,
                    extra={'debug_report': report}
                )
                
                print(json.dumps(report, indent=4))

                # Rilancia l'eccezione
                #raise

        return wrapper
    return decorator

# =====================================================================
# --- Funzione Principale di Analisi Finale --- (MODIFICATA)
# =====================================================================

def analyze_exception_with_module_structure(
    source_code: str, 
    custom_filename: str = "<code_in_memory>", 
    app_context: Dict[str, Any] = None
) -> Dict[str, Any]:
    
    exc_type, exc_value, exc_traceback = sys.exc_info()
    
    if exc_type is None or exc_traceback is None:
        return {"status": "Nessuna eccezione attiva trovata."}
        
    tb_list = traceback.extract_tb(exc_traceback)
    full_traceback_text = traceback.format_exception(exc_type, exc_value, exc_traceback)
    
    last_traceback = exc_traceback
    while last_traceback.tb_next:
        last_traceback = last_traceback.tb_next
    last_frame_object = last_traceback.tb_frame 
    
    raw_filename = tb_list[-1].filename
    raw_lineno = tb_list[-1].lineno
    
    source_to_analyze = source_code
    analysis_filename = custom_filename
    report_filename = raw_filename
    
    # Tenta di caricare il codice sorgente dal disco se non è in memoria
    if raw_filename.startswith('<'):
        if custom_filename != "<code_in_memory>":
            report_filename = custom_filename
    else:
        source_from_disk = _get_source_code_from_disk(raw_filename)
        if source_from_disk:
            source_to_analyze = source_from_disk
            analysis_filename = raw_filename
            report_filename = raw_filename
            
    # La riga di codice non è più recuperata qui.

    module_structure = get_module_structure_from_string_fixed(source_to_analyze, analysis_filename)
    structured_tb = extract_detailed_traceback(exc_traceback) 
    
    # Recupera i dettagli dell'errore finale dal traceback strutturato (più affidabile)
    final_error_step = structured_tb[-1] if structured_tb else {
        "step_code_line": "SORGENTE NON RECUPERATA", 
        "step_lineno": raw_lineno, 
        "step_function": tb_list[-1].name
    }
    
    final_local_vars = {
         k: sanitize_variable_value(k, v) for k, v in last_frame_object.f_locals.items() 
         if not k.startswith('__') and k not in ['last_traceback', 'last_frame_object', 'raw_lineno', 'tb_list', 'exc_traceback']
    }
    
    exception_details = {
        "exception_type": type(exc_value).__name__,
        "exception_message": str(exc_value),
        "error_location": {
            "filename": report_filename,
            "line_number": final_error_step["step_lineno"],
            "function_name": final_error_step["step_function"],
            "source_code_line": final_error_step["step_code_line"], # <- Usa il valore da structured_tb
        },
        "LOCAL_VARIABLES_STATE_FINAL_FRAME": final_local_vars,
    }
    
    debug_report = {
        "ENVIRONMENT_CONTEXT": {
            "timestamp": datetime.datetime.now().isoformat(),
            "python_version": platform.python_version(),
            **_get_system_info()
        },
        "APPLICATION_CONTEXT": app_context or {"VERSION": "N/A", "USER_ID": "anonymous"},
        "EXCEPTION_DETAILS": exception_details,
        "MODULE_STRUCTURE_ANALYSIS": module_structure,
        "STRUCTURED_TRACEBACK": structured_tb, 
        #"FULL_TRACEBACK_TEXT": full_traceback_text 
    }
    
    return debug_report

# =====================================================================
# --- Blocco di Simulazione e Test (AGGIUNTO SCENARIO 2) ---
# =====================================================================

APP_CONTEXT = {
    "APP_VERSION": "1.2.5",
    "USER_ID": "user_1234",
    "REQUEST_ID": "req_xyz987"
}

if __name__ == "__main__":
    # ------------------------------------------------------------------
    # --- SCENARIO 2: Errore gestito tramite Decoratore (@capture_errors) ---
    # ------------------------------------------------------------------
    
    def multiply_or_fail(a, b):
        """Funzione con un potenziale bug di tipo."""
        # Se b è None, genera TypeError
        return a * b

    @capture_errors(
        custom_filename=os.path.basename(__file__),
        app_context=APP_CONTEXT
    )
    def main_process_with_error(data):
        """Funzione principale decorata che chiama la funzione buggata."""
        x = data.get("x", 1)
        y = data.get("y") # y sarà None
        some_sensitive_data = "passw"
        
        # Linea che causerà l'errore (TypeError: int * NoneType)
        result = multiply_or_fail(x, y) 
        
        # Variabili locali: x=1, y=None, some_sensitive_data='passw'
        return result

    print("\n" + "#"*60)
    print("INIZIO TEST SCENARIO 2: Decoratore @capture_errors (gestisce l'errore e lo rilancia)")
    print("#"*60)

    data_input = {"x": 100}
        # La chiamata fallisce, il decoratore intercetta, logga e rilancia.
    main_process_with_error(data_input)