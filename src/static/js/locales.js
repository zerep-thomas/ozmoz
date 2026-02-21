/* --- static/js/locales.js --- */

window.locales = {
  fr: {
    // --- LANGUAGE TRANSLATIONS (For the dropdown) ---
    lang_autodetect: "Détection automatique",
    lang_fr: "Français",
    lang_en: "Anglais",
    lang_de: "Allemand",
    lang_de_ch: "Allemand (Suisse)",
    lang_es: "Espagnol",
    lang_it: "Italien",
    lang_pt: "Portugais",
    lang_ja: "Japonais",
    lang_ko: "Coréen",
    lang_zh: "Chinois (Simplifié)",
    lang_zh_hk: "Chinois (Hong Kong)",
    lang_zh_tw: "Chinois (Traditionnel)",
    lang_ru: "Russe",
    lang_nl: "Néerlandais",
    lang_nl_be: "Flamand",
    lang_pl: "Polonais",
    lang_tr: "Turc",
    lang_hi: "Hindi",
    lang_sv: "Suédois",
    lang_da: "Danois",
    lang_fi: "Finnois",
    lang_no: "Norvégien",
    lang_bg: "Bulgare",
    lang_et: "Estonien",
    lang_el: "Grec",
    lang_hu: "Hongrois",
    lang_id: "Indonésien",
    lang_lv: "Letton",
    lang_lt: "Lituanien",
    lang_ms: "Malais",
    lang_ro: "Roumain",
    lang_sk: "Slovaque",
    lang_cs: "Tchèque",
    lang_th: "Thaï",
    lang_uk: "Ukrainien",
    lang_vi: "Vietnamien",

    // Sidebar
    sidebar_home: "Accueil",
    sidebar_general: "Général",
    sidebar_history: "Historique",
    sidebar_replacement: "Remplacer",
    sidebar_agent: "Agent",
    sidebar_logs: "Logs",
    sidebar_update: "Mettre à jour",

    // Dashboard
    dash_dictated_words: "🚀 Mots dictés",
    dash_avg_speed: "⚡ Vitesse moyenne",
    dash_time_saved: "🏆 Temps économisé",
    dash_activity: "Aperçu de l'activité",
    chart_label_words: "Mots dictés",
    unit_mpm: " mpm",
    unit_sec: " sec",
    unit_min: " min",

    // General - Tabs
    tab_preferences: "Préférences",
    tab_controls: "Contrôles",
    tab_api: "Clés API",

    // General - Preferences
    header_settings: "Paramètres généraux",
    lbl_model_ai: "Modèle d'IA",
    desc_model_ai:
      "Choisissez le modèle d'intelligence artificielle pour le traitement.",
    tooltip_model_ai:
      "Choisissez le modèle qui correspond à votre besoin en fonction de leurs points forts inscrits à droite",
    loading_models: "Chargement des modèles...",

    lbl_model_audio: "Modèle de Transcription Audio",
    desc_model_audio: "Choisissez le modèle pour la conversion audio-texte.",
    tooltip_model_audio:
      "Choisissez entre la rapidité et la précision sur des mots plus spécialisés",

    lbl_lang: "Langue de transcription",
    desc_lang: "Sélectionnez la langue principale (Interface & Transcription).",
    loading_langs: "Chargement des langues...",

    group_interface: "Interface",
    lbl_chart_type: "Afficher les statistiques sous forme de courbes",
    lbl_dev_mode: "Mode développeur",

    group_audio: "Audio",
    lbl_sounds: "Sons d'interaction",
    lbl_mute: "Couper le son pendant l'utilisation",

    // General - Controls
    hk_visibility: "Afficher/masquer l'onglet",
    hk_record: "Démarrer/Arrêter l'enregistrement",
    hk_ai: "Génération IA (Appuyer/Maintenir)",
    hk_web: "Recherche Web (Appuyer/Maintenir)",
    hk_vision: "Vision de l'écran (Appuyer/Maintenir)",
    btn_modify: "Modifier",

    // General - API
    api_title_audio: "Traitement Audio",
    api_desc_audio:
      "Transcription vocale (STT). Entrer la clé Groq permet d'utiliser les modèles whisper et Deepgram pour nova.",
    api_title_ai: "Génération IA",
    api_desc_ai:
      "Intelligence artificielle (LLM). Entrer les clés pour utiliser les modèles spécifiques.",
    api_separator: "ET / OU",

    // History
    header_history: "Historique des transcriptions",
    ph_search_history: "Rechercher dans l'historique...",
    sort_recent: "Récents",
    sort_old: "Anciens",
    btn_clear_history: "Effacer l'historique",
    no_transcripts: "Aucune transcription trouvée.",
    no_results: "Aucun résultat pour votre recherche.",
    btn_copy: "Copier",
    copied: "Copié",

    // Replacements
    header_replacement: "Remplacement de mots",
    desc_replacement:
      "Créez des remplacements personnalisés appliqués automatiquement.",
    ph_word_origin: "Mot à remplacer",
    ph_word_new: "Nouveau mot",
    btn_add: "Ajouter",
    ph_filter_rep: "Filtrer les remplacements...",
    no_replacements: "Aucun remplacement défini pour l'instant.",
    no_rep_match: "Aucun remplacement ne correspond à votre filtre.",

    // Agents
    header_agents: "Agents",
    desc_agents: "Créez et gérez des agents d'IA.",
    btn_new_agent: "Nouvel agent",
    ph_search_agent: "Rechercher des agents...",
    no_agents: "Aucun agent défini pour le moment.",
    status_active: "Actif",
    status_inactive: "Inactif",
    btn_edit: "Modifier",
    btn_delete: "Supprimer",

    // Logs
    header_logs: "Logs de l'Application",
    btn_refresh: "Rafraîchir",
    btn_export: "Exporter",
    ph_search_logs: "Rechercher dans les logs...",

    // Modals & Dynamic
    modal_hotkey_title: "Modifier le raccourci",
    modal_hotkey_desc:
      "Appuyez sur la combinaison de touches souhaitée (ex: Ctrl+Alt+X)",
    modal_waiting: "En attente de saisie...",
    btn_cancel: "Annuler",
    btn_save: "Enregistrer",
    modal_confirm_title: "Êtes-vous sûr ?",
    modal_confirm_title: "¿Está seguro?",
    confirm_clear_history_text:
      "Êtes-vous sûr de vouloir supprimer tout l'historique ? Cette action est irréversible.",
    modal_agent_create_title: "Créer un nouvel agent",
    modal_agent_edit_title: "Modifier l'Agent",
    lbl_agent_name: "Nom de l'agent",
    desc_agent_name: "Donnez à votre agent un nom descriptif",
    ph_agent_name: "Entrez le nom de l'agent",
    lbl_agent_trigger: "Mot/Phrase d'activation",
    desc_agent_trigger: "Définissez un mot-clé pour déclencher cet agent",
    ph_agent_trigger: "Entrez le mot d'activation (obligatoire)",
    lbl_agent_autopaste: "Collage Automatique",
    desc_agent_autopaste: "Colle automatiquement la réponse.",
    lbl_agent_vision: "Vision de l'écran",
    desc_agent_vision: "Permet à l'agent de voir votre écran.",
    lbl_agent_prompt: "Instruction système",
    desc_agent_prompt: "Définissez le comportement de l'agent",
    ph_agent_prompt: "Entrez les instructions...",
    btn_create_agent: "Créer l'agent",
    btn_save_changes: "Enregistrer les modifications",

    toast_copied: "Copié",
    toast_error: "Erreur",
    toast_success: "Succès",

    dash_7_days: "7 Jours",
    dash_30_days: "30 Jours",
    sort_recent: "Récents",
    sort_old: "Anciens",

    confirm_delete_agent: 'Supprimer l\'agent "{name}" ?',
    confirm_delete_replacement:
      'Supprimer le remplacement "{word1}" → "{word2}" ?',
    modal_waiting_input: "En attente de saisie...",

    saving: "Sauvegarde...",
    saved: "Sauvegardé !",
    btn_error: "Erreur",
    model_incompatible_web: "Ce modèle est incompatible avec la Recherche Web.",
    model_incompatible_vision:
      "Ce modèle n'est pas multimodal et incompatible avec la Vision.",
    model_incompatible_generic: "Modèle sélectionné incompatible.",
    missing_api_key_msg: "Clé API manquante pour <b>{provider}</b>.",
    loading: "Chargement...",
    no_models: "Vous avez besoin d'entrer une clé API",
    error_loading: "Erreur",

    // --- Local Model Modal ---
    modal_local_title: "Téléchargement Requis",
    modal_local_desc:
      "Pour utiliser la transcription hors-ligne, le modèle Whisper V3 Turbo doit être téléchargé.",
    modal_local_size: "Taille : ~1.8 GB",
    modal_local_progress:
      "Téléchargement en cours (cela peut prendre quelques minutes)...",
    btn_download_install: "Télécharger & Installer",

    // --- Model Badges ---
    badge_downloading: "Téléchargement...",
    badge_ready_local: "Local",
    badge_need_download: "À télécharger",
    badge_standard: "Standard",

    // --- Local Model Modal ---
    modal_delete_local_title: "Supprimer le modèle ?",
    modal_delete_local_text:
      'Voulez-vous supprimer "{model}" ?\n({size} seront libérés)',
    btn_delete_short: "Supprimer",
  },
  en: {
    lang_autodetect: "Auto Detect",
    lang_fr: "French",
    lang_en: "English",
    lang_de: "German",
    lang_de_ch: "German (Swiss)",
    lang_es: "Spanish",
    lang_it: "Italian",
    lang_pt: "Portuguese",
    lang_ja: "Japanese",
    lang_ko: "Korean",
    lang_zh: "Chinese (Simplified)",
    lang_zh_hk: "Chinese (Hong Kong)",
    lang_zh_tw: "Chinese (Traditional)",
    lang_ru: "Russian",
    lang_nl: "Dutch",
    lang_nl_be: "Flemish",
    lang_pl: "Polish",
    lang_tr: "Turkish",
    lang_hi: "Hindi",
    lang_sv: "Swedish",
    lang_da: "Danish",
    lang_fi: "Finnish",
    lang_no: "Norwegian",
    lang_bg: "Bulgarian",
    lang_et: "Estonian",
    lang_el: "Greek",
    lang_hu: "Hungarian",
    lang_id: "Indonesian",
    lang_lv: "Latvian",
    lang_lt: "Lithuanian",
    lang_ms: "Malay",
    lang_ro: "Romanian",
    lang_sk: "Slovak",
    lang_cs: "Czech",
    lang_th: "Thai",
    lang_uk: "Ukrainian",
    lang_vi: "Vietnamese",

    // Sidebar
    sidebar_home: "Home",
    sidebar_general: "General",
    sidebar_history: "History",
    sidebar_replacement: "Replace",
    sidebar_agent: "Agent",
    sidebar_logs: "Logs",
    sidebar_update: "Update",

    // Dashboard
    dash_dictated_words: "🚀 Dictated Words",
    dash_avg_speed: "⚡ Avg Speed",
    dash_time_saved: "🏆 Time Saved",
    dash_activity: "Activity Overview",
    chart_label_words: "Dictated words",
    unit_mpm: " wpm",
    unit_sec: " sec",
    unit_min: " min",

    // General - Tabs
    tab_preferences: "Preferences",
    tab_controls: "Controls",
    tab_api: "API Keys",

    // General - Preferences
    header_settings: "General Settings",
    lbl_model_ai: "AI Model",
    desc_model_ai: "Choose the Artificial Intelligence model for processing.",
    tooltip_model_ai:
      "Choose the model that fits your needs based on their strengths listed on the right",
    loading_models: "Loading models...",

    lbl_model_audio: "Audio Transcription Model",
    desc_model_audio: "Choose the model for speech-to-text conversion.",
    tooltip_model_audio:
      "Choose between speed and accuracy for specialized words",

    lbl_lang: "Transcription Language",
    desc_lang: "Select the main language (Interface & Transcription).",
    loading_langs: "Loading languages...",

    group_interface: "Interface",
    lbl_chart_type: "Display statistics as lines",
    lbl_dev_mode: "Developer Mode",

    group_audio: "Audio",
    lbl_sounds: "Interaction Sounds",
    lbl_mute: "Mute system during use",

    // General - Controls
    hk_visibility: "Show/Hide Tab",
    hk_record: "Start/Stop Recording",
    hk_ai: "AI Generation (Press/Hold)",
    hk_web: "Web Search (Press/Hold)",
    hk_vision: "Screen Vision (Press/Hold)",
    btn_modify: "Edit",

    // General - API
    api_title_audio: "Audio Processing",
    api_desc_audio:
      "Speech-to-text (STT). Enter Groq key for Whisper models and Deepgram key for Nova.",
    api_title_ai: "AI Generation",
    api_desc_ai:
      "Artificial Intelligence (LLM). Enter keys to use specific models.",
    api_separator: "AND / OR",

    // History
    header_history: "Transcription History",
    ph_search_history: "Search history...",
    sort_recent: "Recent",
    sort_old: "Oldest",
    btn_clear_history: "Clear History",
    no_transcripts: "No transcriptions found.",
    no_results: "No results for your search.",
    btn_copy: "Copy",
    copied: "Copied",

    // Replacements
    header_replacement: "Word Replacement",
    desc_replacement: "Create custom replacements applied automatically.",
    ph_word_origin: "Word to replace",
    ph_word_new: "New word",
    btn_add: "Add",
    ph_filter_rep: "Filter replacements...",
    no_replacements: "No replacements defined yet.",
    no_rep_match: "No replacement matches your filter.",

    // Agents
    header_agents: "Agents",
    desc_agents: "Create and manage AI agents.",
    btn_new_agent: "New Agent",
    ph_search_agent: "Search agents...",
    no_agents: "No agents defined yet.",
    status_active: "Active",
    status_inactive: "Inactive",
    btn_edit: "Edit",
    btn_delete: "Delete",

    // Logs
    header_logs: "Application Logs",
    btn_refresh: "Refresh",
    btn_export: "Export",
    ph_search_logs: "Search logs...",

    // Modals & Dynamic
    modal_hotkey_title: "Edit Hotkey",
    modal_hotkey_desc: "Press the desired key combination (e.g., Ctrl+Alt+X)",
    modal_waiting: "Waiting for input...",
    btn_cancel: "Cancel",
    btn_save: "Save",
    modal_confirm_title: "Are you sure?",
    confirm_clear_history_text:
      "Are you sure you want to delete all history? This action is irreversible.",
    modal_agent_create_title: "Create New Agent",
    modal_agent_edit_title: "Edit Agent",
    lbl_agent_name: "Agent Name",
    desc_agent_name: "Give your agent a descriptive name",
    ph_agent_name: "Enter agent name",
    lbl_agent_trigger: "Trigger Word/Phrase",
    desc_agent_trigger: "Define a keyword to trigger this agent",
    ph_agent_trigger: "Enter trigger word (obligatory)",
    lbl_agent_autopaste: "Auto-Paste",
    desc_agent_autopaste: "Automatically pastes the response.",
    lbl_agent_vision: "Screen Vision",
    desc_agent_vision: "Allows the agent to see your screen.",
    lbl_agent_prompt: "System Prompt",
    desc_agent_prompt: "Define the agent's behavior",
    ph_agent_prompt: "Enter system instructions...",
    btn_create_agent: "Create Agent",
    btn_save_changes: "Save Changes",

    toast_copied: "Copied",
    toast_error: "Error",
    toast_success: "Success",

    dash_7_days: "7 Days",
    dash_30_days: "30 Days",
    sort_recent: "Recent",
    sort_old: "Oldest",

    confirm_delete_agent: 'Delete agent "{name}"?',
    confirm_delete_replacement: 'Delete replacement "{word1}" → "{word2}"?',
    modal_waiting_input: "Waiting for input...",

    saving: "Saving...",
    saved: "Saved!",
    btn_error: "Error",
    model_incompatible_web: "This model is incompatible with Web Search.",
    model_incompatible_vision:
      "This model is not multimodal and incompatible with Screen Vision.",
    model_incompatible_generic: "Incompatible model selected.",
    missing_api_key_msg: "Missing API Key for <b>{provider}</b>.",
    loading: "Loading...",
    no_models: "You need to enter an API key",
    error_loading: "Error",

    // --- Local Model Modal ---
    modal_local_title: "Download Required",
    modal_local_desc:
      "To use offline transcription, the Whisper V3 Turbo model must be downloaded.",
    modal_local_size: "Size: ~1.8 GB",
    modal_local_progress:
      "Downloading in progress (this may take a few minutes)...",
    btn_download_install: "Download & Install",

    // --- Model Badges ---
    badge_downloading: "Downloading...",
    badge_ready_local: "Local",
    badge_need_download: "Download",
    badge_standard: "Standard",

    // --- Local Model Modal ---
    modal_delete_local_title: "Delete model?",
    modal_delete_local_text:
      'Do you want to delete "{model}"?\n({size} will be freed)',
    btn_delete_short: "Delete",
  },
  es: {
    lang_autodetect: "Detección automática",
    lang_fr: "Francés",
    lang_en: "Inglés",
    lang_de: "Alemán",
    lang_de_ch: "Alemán (Suiza)",
    lang_es: "Español",
    lang_it: "Italiano",
    lang_pt: "Portugués",
    lang_ja: "Japonés",
    lang_ko: "Coreano",
    lang_zh: "Chino (Simplificado)",
    lang_zh_hk: "Chino (Hong Kong)",
    lang_zh_tw: "Chino (Tradicional)",
    lang_ru: "Ruso",
    lang_nl: "Holandés",
    lang_nl_be: "Flamenco",
    lang_pl: "Polaco",
    lang_tr: "Turco",
    lang_hi: "Hindi",
    lang_sv: "Sueco",
    lang_da: "Danés",
    lang_fi: "Finlandés",
    lang_no: "Noruego",
    lang_bg: "Búlgaro",
    lang_et: "Estonio",
    lang_el: "Griego",
    lang_hu: "Húngaro",
    lang_id: "Indonesio",
    lang_lv: "Letón",
    lang_lt: "Lituano",
    lang_ms: "Malayo",
    lang_ro: "Rumano",
    lang_sk: "Eslovaco",
    lang_cs: "Checo",
    lang_th: "Tailandés",
    lang_uk: "Ucraniano",
    lang_vi: "Vietnamita",

    // Sidebar
    sidebar_home: "Inicio",
    sidebar_general: "General",
    sidebar_history: "Historial",
    sidebar_replacement: "Reemplazar",
    sidebar_agent: "Agente",
    sidebar_logs: "Registros",
    sidebar_update: "Actualizar",

    // Dashboard
    dash_dictated_words: "🚀 Palabras dictadas",
    dash_avg_speed: "⚡ Velocidad media",
    dash_time_saved: "🏆 Tiempo ahorrado",
    dash_activity: "Resumen de actividad",
    chart_label_words: "Palabras dictadas",
    unit_mpm: " ppm",
    unit_sec: " seg",
    unit_min: " min",

    // General - Tabs
    tab_preferences: "Preferencias",
    tab_controls: "Controles",
    tab_api: "Claves API",

    // General - Preferences
    header_settings: "Configuración general",
    lbl_model_ai: "Modelo de IA",
    desc_model_ai:
      "Elija el modelo de Inteligencia Artificial para el procesamiento.",
    tooltip_model_ai:
      "Elija el modelo que se ajuste a sus necesidades según sus puntos fuertes listados a la derecha",
    loading_models: "Cargando modelos...",

    lbl_model_audio: "Modelo de Transcripción de Audio",
    desc_model_audio: "Elija el modelo para la conversión de audio a texto.",
    tooltip_model_audio:
      "Elija entre velocidad y precisión para palabras especializadas",

    lbl_lang: "Idioma de transcripción",
    desc_lang: "Seleccione el idioma principal (Interfaz y Transcripción).",
    loading_langs: "Cargando idiomas...",

    group_interface: "Interfaz",
    lbl_chart_type: "Mostrar estadísticas como líneas",
    lbl_dev_mode: "Modo desarrollador",

    group_audio: "Audio",
    lbl_sounds: "Sonidos de interacción",
    lbl_mute: "Silenciar sistema durante el uso",

    // General - Controls
    hk_visibility: "Mostrar/Ocultar pestaña",
    hk_record: "Iniciar/Detener grabación",
    hk_ai: "Generación IA (Presionar/Mantener)",
    hk_web: "Búsqueda Web (Presionar/Mantener)",
    hk_vision: "Visión de pantalla (Presionar/Mantener)",
    btn_modify: "Editar",

    // General - API
    api_title_audio: "Procesamiento de Audio",
    api_desc_audio:
      "Transcripción de voz (STT). Ingrese la clave Groq para modelos Whisper y Deepgram para Nova.",
    api_title_ai: "Generación IA",
    api_desc_ai:
      "Inteligencia Artificial (LLM). Ingrese las claves para usar modelos específicos.",
    api_separator: "Y / O",

    // History
    header_history: "Historial de Transcripciones",
    ph_search_history: "Buscar en el historial...",
    sort_recent: "Recientes",
    sort_old: "Antiguos",
    btn_clear_history: "Borrar Historial",
    no_transcripts: "No se encontraron transcripciones.",
    no_results: "Sin resultados para su búsqueda.",
    btn_copy: "Copiar",
    copied: "Copiado",

    // Replacements
    header_replacement: "Reemplazo de palabras",
    desc_replacement:
      "Cree reemplazos personalizados aplicados automáticamente.",
    ph_word_origin: "Palabra a reemplazar",
    ph_word_new: "Nueva palabra",
    btn_add: "Añadir",
    ph_filter_rep: "Filtrar reemplazos...",
    no_replacements: "No hay reemplazos definidos todavía.",
    no_rep_match: "Ningún reemplazo coincide con su filtro.",

    // Agents
    header_agents: "Agentes",
    desc_agents: "Cree y gestione agentes de IA.",
    btn_new_agent: "Nuevo Agente",
    ph_search_agent: "Buscar agentes...",
    no_agents: "No hay agentes definidos por el momento.",
    status_active: "Activo",
    status_inactive: "Inactivo",
    btn_edit: "Editar",
    btn_delete: "Eliminar",

    // Logs
    header_logs: "Registros de la Aplicación",
    btn_refresh: "Actualizar",
    btn_export: "Exportar",
    ph_search_logs: "Buscar registros...",

    // Modals & Dynamic
    modal_hotkey_title: "Editar atajo",
    modal_hotkey_desc:
      "Presione la combinación de teclas deseada (ej: Ctrl+Alt+X)",
    modal_waiting: "Esperando entrada...",
    btn_cancel: "Cancelar",
    btn_save: "Guardar",
    modal_confirm_title: "¿Está seguro?",
    modal_agent_create_title: "Crear Nuevo Agente",
    modal_agent_edit_title: "Editar Agente",
    lbl_agent_name: "Nombre del Agente",
    desc_agent_name: "Dé a su agente un nombre descriptivo",
    ph_agent_name: "Ingrese el nombre del agente",
    lbl_agent_trigger: "Palabra/Frase de activación",
    desc_agent_trigger: "Defina una palabra clave para activar este agente",
    ph_agent_trigger: "Ingrese la palabra de activación (obligatorio)",
    lbl_agent_autopaste: "Pegado Automático",
    desc_agent_autopaste: "Pega automáticamente la respuesta.",
    lbl_agent_vision: "Visión de Pantalla",
    desc_agent_vision: "Permite al agente ver su pantalla.",
    lbl_agent_prompt: "Instrucción del Sistema",
    desc_agent_prompt: "Defina el comportamiento del agente",
    ph_agent_prompt: "Ingrese las instrucciones...",
    btn_create_agent: "Crear Agente",
    btn_save_changes: "Guardar Cambios",

    toast_copied: "Copiado",
    toast_error: "Error",
    toast_success: "Éxito",

    dash_7_days: "7 Días",
    dash_30_days: "30 Días",
    sort_recent: "Recientes",
    sort_old: "Antiguos",

    confirm_delete_agent: '¿Eliminar el agente "{name}"?',
    confirm_delete_replacement: '¿Eliminar reemplazo "{word1}" → "{word2}"?',
    modal_waiting_input: "Esperando entrada...",

    saving: "Guardando...",
    saved: "¡Guardado!",
    btn_error: "Error",
    model_incompatible_web: "Este modelo es incompatible con Búsqueda Web.",
    model_incompatible_vision:
      "Este modelo no es multimodal e incompatible con Visión.",
    model_incompatible_generic: "Modelo seleccionado incompatible.",
    missing_api_key_msg: "Falta la clave API para <b>{provider}</b>.",
    loading: "Cargando...",
    no_models: "Necesitas ingresar una clave API",
    error_loading: "Error",

    // --- Local Model Modal ---
    modal_local_title: "Descarga requerida",
    modal_local_desc:
      "Para usar la transcripción sin conexión, el modelo Whisper V3 Turbo debe descargarse.",
    modal_local_size: "Tamaño: ~1.8 GB",
    modal_local_progress:
      "Descarga en curso (esto puede tardar unos minutos)...",
    btn_download_install: "Descargar e instalar",

    // --- Model Badges ---
    badge_downloading: "Descargando...",
    badge_ready_local: "Local",
    badge_need_download: "Para descargar",
    badge_standard: "Estándar",

    // --- Local Model Modal ---
    modal_delete_local_title: "¿Eliminar modelo?",
    modal_delete_local_text:
      '¿Quieres eliminar "{model}"?\n({size} serán liberados)',
    btn_delete_short: "Eliminar",
  },
};
