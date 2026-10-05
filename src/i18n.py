"""Texts of the application and of the generated documents, in every language.

The language chosen in the settings tab applies to both: the window is redrawn
and the next Excel and PDF files are written with it. Adding a language is a
matter of adding one more entry to LANGUAGES, UI and OUTPUT.
"""

import locale

import settings

LANGUAGES = {'en': 'English', 'ca': 'Català', 'es': 'Castellano'}
DEFAULT_LANGUAGE = 'en'

# ------------------------------------------------------------
# Window: buttons, labels, dialogs and status messages
# ------------------------------------------------------------
UI = {
    'en': {
        'window_title': "Survey Tabulator · .sav",
        'app_title': "Survey Tabulator",
        'open_file': "📂  Open data file (.sav)",
        'no_file': "No file loaded",
        'file_info': "📄 {name}   ·   {rows} rows   ·   {variables} variables",
        'tab_variables': "📊 Variables",
        'tab_settings': "⚙️ Settings",
        'available': "Available variables",
        'selected': "Selected variables",
        'add': "Add  ▶",
        'add_all': "Add all  ▶▶",
        'remove': "◀  Remove",
        'clear': "◀◀  Clear",
        'counter': "{available} available · {selected} selected",
        'generate': "⚙  Generate tables",
        'cancel': "✖  Cancel",
        'cancelling': "Cancelling...",
        'cancelled': "Cancelled",
        'ready': "Ready",
        'output_frame': " Output ",
        'export_format': "Export format:",
        'both': "Both",
        'rows_per_block': "Rows read per block:",
        'show_total': "Show the overall 'Total' column/row in the tables",
        'show_stats': "Compute mean and standard deviation for 0-10 and 1-10 scales",
        'language_frame': " Language ",
        'language_hint': "Language of the application and of the generated Excel and PDF files.",
        'columns_frame': " Columns of this file ",
        'column_year': "Year / wave:",
        'column_weight': "Weight:",
        'column_online_weight': "Online weight:",
        'column_none': "(none)",
        'year_frame': " Year filter ",
        'year_hint': "Tick the years to include in the document.",
        'year_placeholder': "Load a .sav file to detect the available years...",
        'year_scanning': "Scanning the years in the file...",
        'year_single': "No year column selected: the file will be processed as a single block.",
        'year_empty': "The '{column}' column has no valid data.",
        'special_frame': " Special values ",
        'special_hint': "Tick the answers (2222, 4444...) to INCLUDE explicitly in the document.\n"
                        "Unticked ones are left out so that they do not distort the valid percentages.",
        'special_placeholder': "Load a .sav file to see the codes it uses...",
        'special_none': "This file does not use any of the usual special codes.",
        'open_title': "Open .sav file",
        'save_title': "Save as",
        'type_sav': "SPSS .sav",
        'type_all': "All files",
        'type_excel': "Excel files",
        'type_pdf': "PDF files",
        'type_both': "Excel + PDF (both are written)",
        'error': "Error",
        'warning': "Warning",
        'done': "Done",
        'read_failed': "The file could not be read:\n{error}",
        'load_failed': "Loading failed",
        'need_file': "Load a .sav file first",
        'need_variables': "There are no selected variables to process",
        'need_chunk_size': "The block size must be a positive integer",
        'need_year': "Select at least one year.",
        'confirm_unweighted': "No weight column is selected in the settings tab, so the tables will count "
                              "every interview as one (unweighted).\n\nGenerate them anyway?",
        'wait_scan': "The years of the file are still being scanned. Try again in a moment.",
        'generating': "Generating...",
        'stage_read': "Reading block {done}/{total}",
        'stage_excel': "Excel: {detail} ({done}/{total})",
        'stage_pdf': "PDF: {detail} ({done}/{total})",
        'stage_pdf_render': "Rendering PDF (writing to disk...)",
        'generated': "✔ Generated: {names}",
        'generated_message': "File(s) generated:\n{paths}",
        'generation_failed': "✖ Generation failed",
        'generation_failed_message': "Generation failed:\n{error}",
    },
    'ca': {
        'window_title': "Survey Tabulator · .sav",
        'app_title': "Survey Tabulator",
        'open_file': "📂  Obre la matriu (.sav)",
        'no_file': "Cap fitxer carregat",
        'file_info': "📄 {name}   ·   {rows} files   ·   {variables} variables",
        'tab_variables': "📊 Variables",
        'tab_settings': "⚙️ Configuració",
        'available': "Variables disponibles",
        'selected': "Variables seleccionades",
        'add': "Afegeix  ▶",
        'add_all': "Totes  ▶▶",
        'remove': "◀  Treu",
        'clear': "◀◀  Neteja",
        'counter': "{available} disponibles · {selected} seleccionades",
        'generate': "⚙  Genera les taules",
        'cancel': "✖  Cancel·la",
        'cancelling': "S'està cancel·lant...",
        'cancelled': "Cancel·lat",
        'ready': "A punt",
        'output_frame': " Sortida ",
        'export_format': "Format d'exportació:",
        'both': "Tots dos",
        'rows_per_block': "Files llegides per bloc:",
        'show_total': "Mostra la columna/fila de 'Total' global a les taules",
        'show_stats': "Calcula la mitjana i la desviació en escales 0-10 i 1-10",
        'language_frame': " Idioma ",
        'language_hint': "Idioma de l'aplicació i dels fitxers Excel i PDF que es generen.",
        'columns_frame': " Columnes d'aquest fitxer ",
        'column_year': "Any / onada:",
        'column_weight': "Ponderació:",
        'column_online_weight': "Ponderació en línia:",
        'column_none': "(cap)",
        'year_frame': " Filtre d'anys ",
        'year_hint': "Marca els anys que vols incloure al document.",
        'year_placeholder': "Carrega un fitxer .sav per detectar els anys disponibles...",
        'year_scanning': "S'estan cercant els anys del fitxer...",
        'year_single': "No hi ha cap columna d'any seleccionada: el fitxer es processarà com un únic bloc.",
        'year_empty': "La columna '{column}' no té dades vàlides.",
        'special_frame': " Valors especials ",
        'special_hint': "Marca les respostes (2222, 4444...) que vols INCLOURE explícitament al document.\n"
                        "Les desmarcades s'exclouen per no alterar els percentatges vàlids.",
        'special_placeholder': "Carrega un fitxer .sav per veure els codis que fa servir...",
        'special_none': "Aquest fitxer no fa servir cap dels codis especials habituals.",
        'open_title': "Obre un fitxer .sav",
        'save_title': "Desa com a",
        'type_sav': "SPSS .sav",
        'type_all': "Tots els fitxers",
        'type_excel': "Fitxers d'Excel",
        'type_pdf': "Fitxers PDF",
        'type_both': "Excel + PDF (es generen tots dos)",
        'error': "Error",
        'warning': "Avís",
        'done': "Fet",
        'read_failed': "No s'ha pogut llegir el fitxer:\n{error}",
        'load_failed': "Error en carregar",
        'need_file': "Primer cal carregar un fitxer .sav",
        'need_variables': "No hi ha cap variable seleccionada per processar",
        'need_chunk_size': "La mida del bloc ha de ser un enter positiu",
        'need_year': "Selecciona almenys un any.",
        'confirm_unweighted': "No hi ha cap columna de ponderació seleccionada a la pestanya de configuració, "
                              "de manera que les taules comptaran cada entrevista com a una (sense ponderar)."
                              "\n\nVols generar-les igualment?",
        'wait_scan': "Encara s'estan cercant els anys del fitxer. Torna-ho a provar d'aquí a un moment.",
        'generating': "S'està generant...",
        'stage_read': "Llegint el bloc {done}/{total}",
        'stage_excel': "Excel: {detail} ({done}/{total})",
        'stage_pdf': "PDF: {detail} ({done}/{total})",
        'stage_pdf_render': "Renderitzant el PDF (desant al disc...)",
        'generated': "✔ Generat: {names}",
        'generated_message': "Fitxer(s) generat(s):\n{paths}",
        'generation_failed': "✖ Error en generar",
        'generation_failed_message': "Error en generar:\n{error}",
    },
    'es': {
        'window_title': "Survey Tabulator · .sav",
        'app_title': "Survey Tabulator",
        'open_file': "📂  Abrir matriz (.sav)",
        'no_file': "Ningún archivo cargado",
        'file_info': "📄 {name}   ·   {rows} filas   ·   {variables} variables",
        'tab_variables': "📊 Variables",
        'tab_settings': "⚙️ Configuración",
        'available': "Variables disponibles",
        'selected': "Variables seleccionadas",
        'add': "Añadir  ▶",
        'add_all': "Todas  ▶▶",
        'remove': "◀  Quitar",
        'clear': "◀◀  Limpiar",
        'counter': "{available} disponibles · {selected} seleccionadas",
        'generate': "⚙  Generar tablas",
        'cancel': "✖  Cancelar",
        'cancelling': "Cancelando...",
        'cancelled': "Cancelado",
        'ready': "Listo",
        'output_frame': " Salida ",
        'export_format': "Formato de exportación:",
        'both': "Ambos",
        'rows_per_block': "Filas leídas por bloque:",
        'show_total': "Mostrar la columna/fila de 'Total' global en las tablas",
        'show_stats': "Calcular la media y la desviación en escalas 0-10 y 1-10",
        'language_frame': " Idioma ",
        'language_hint': "Idioma de la aplicación y de los archivos Excel y PDF que se generan.",
        'columns_frame': " Columnas de este archivo ",
        'column_year': "Año / oleada:",
        'column_weight': "Ponderación:",
        'column_online_weight': "Ponderación en línea:",
        'column_none': "(ninguna)",
        'year_frame': " Filtro de años ",
        'year_hint': "Marca los años que quieras incluir en el documento.",
        'year_placeholder': "Carga un archivo .sav para detectar los años disponibles...",
        'year_scanning': "Buscando los años del archivo...",
        'year_single': "No hay ninguna columna de año seleccionada: el archivo se procesará como un único bloque.",
        'year_empty': "La columna '{column}' no tiene datos válidos.",
        'special_frame': " Valores especiales ",
        'special_hint': "Marca las respuestas (2222, 4444...) que quieras INCLUIR explícitamente en el documento.\n"
                        "Las desmarcadas se excluyen para no alterar los porcentajes válidos.",
        'special_placeholder': "Carga un archivo .sav para ver los códigos que utiliza...",
        'special_none': "Este archivo no utiliza ninguno de los códigos especiales habituales.",
        'open_title': "Abrir archivo .sav",
        'save_title': "Guardar como",
        'type_sav': "SPSS .sav",
        'type_all': "Todos los archivos",
        'type_excel': "Archivos de Excel",
        'type_pdf': "Archivos PDF",
        'type_both': "Excel + PDF (se generan los dos)",
        'error': "Error",
        'warning': "Advertencia",
        'done': "Hecho",
        'read_failed': "No se pudo leer el archivo:\n{error}",
        'load_failed': "Error al cargar",
        'need_file': "Primero hay que cargar un archivo .sav",
        'need_variables': "No hay variables seleccionadas para procesar",
        'need_chunk_size': "El tamaño de bloque debe ser un entero positivo",
        'need_year': "Selecciona al menos un año.",
        'confirm_unweighted': "No hay ninguna columna de ponderación seleccionada en la pestaña de configuración, "
                              "así que las tablas contarán cada entrevista como una (sin ponderar)."
                              "\n\n¿Generarlas igualmente?",
        'wait_scan': "Todavía se están buscando los años del archivo. Vuelve a intentarlo en un momento.",
        'generating': "Generando...",
        'stage_read': "Leyendo el bloque {done}/{total}",
        'stage_excel': "Excel: {detail} ({done}/{total})",
        'stage_pdf': "PDF: {detail} ({done}/{total})",
        'stage_pdf_render': "Renderizando el PDF (guardando en disco...)",
        'generated': "✔ Generado: {names}",
        'generated_message': "Archivo(s) generado(s):\n{paths}",
        'generation_failed': "✖ Error al generar",
        'generation_failed_message': "Error al generar:\n{error}",
    },
}

# ------------------------------------------------------------
# Documents: everything printed in the Excel and PDF files
# ------------------------------------------------------------
OUTPUT = {
    'en': {
        'decimal_separator': '.',
        'sheet_frequencies': 'Frequencies',
        'sheet_percentages': 'Column %',
        'total': 'Total',
        'year': 'Year',
        'data': 'Data',
        'counts': 'Counts',
        'percentages': 'Column %',
        'total_base': 'TOTAL base',
        'weighted_base': 'Weighted base: Total',
        'weighted_base_online': 'Weighted base: Online',
        'filtered_question': 'Filtered question',
        'mean': 'Mean',
        'std_dev': 'Std. deviation',
        'pdf_frequency': 'Frequency',
        'pdf_percent': 'Percent',
        'pdf_cumulative': 'Cumulative %',
        'pdf_count': 'N',
        'pdf_title': 'Statistical tables',
    },
    'ca': {
        'decimal_separator': ',',
        'sheet_frequencies': 'Freqüències',
        'sheet_percentages': 'Verticals',
        'total': 'Total',
        'year': 'Any',
        'data': 'Dades',
        'counts': 'Absoluts',
        'percentages': 'Verticals',
        'total_base': 'Base TOTAL',
        'weighted_base': 'Base pond: Total',
        'weighted_base_online': 'Base pond: En línia',
        'filtered_question': 'Pregunta filtrada',
        'mean': 'Mitjana',
        'std_dev': 'Desviació',
        'pdf_frequency': 'Freqüències',
        'pdf_percent': 'Percentatges',
        'pdf_cumulative': '% Acumulat',
        'pdf_count': 'Abs',
        'pdf_title': 'Taules estadístiques',
    },
    'es': {
        'decimal_separator': ',',
        'sheet_frequencies': 'Frecuencias',
        'sheet_percentages': 'Verticales',
        'total': 'Total',
        'year': 'Año',
        'data': 'Datos',
        'counts': 'Absolutos',
        'percentages': 'Verticales',
        'total_base': 'Base TOTAL',
        'weighted_base': 'Base pond: Total',
        'weighted_base_online': 'Base pond: En línea',
        'filtered_question': 'Pregunta filtrada',
        'mean': 'Media',
        'std_dev': 'Desviación',
        'pdf_frequency': 'Frecuencias',
        'pdf_percent': 'Porcentajes',
        'pdf_cumulative': '% Acumulado',
        'pdf_count': 'Abs',
        'pdf_title': 'Tablas estadísticas',
    },
}


def ui_texts(language):
    return UI.get(language, UI[DEFAULT_LANGUAGE])


def output_labels(language):
    return OUTPUT.get(language, OUTPUT[DEFAULT_LANGUAGE])


# ------------------------------------------------------------
# Remembering the choice between sessions
# ------------------------------------------------------------

def system_language():
    """The language of the operating system, if it is one of the supported ones."""
    try:
        code = (locale.getlocale()[0] or '').lower()
    except (ValueError, TypeError):
        code = ''
    if code.startswith(('ca', 'catalan')):
        return 'ca'
    if code.startswith(('es', 'spanish')):
        return 'es'
    return DEFAULT_LANGUAGE


def load_language():
    language = settings.load().get('language')
    return language if language in LANGUAGES else system_language()


def save_language(language):
    settings.update(language=language)