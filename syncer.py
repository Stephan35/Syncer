import os
import sqlite3
import time
import shutil
from tkinter import Tk, Button, Entry, filedialog, StringVar, ttk, messagebox, Frame, Menu, Toplevel, Label
from datetime import datetime

ANALYSE_DB = 'syncer_analyse.db'
CONFIG_DB = 'syncer.db'
DELTA = 15  # Delta en secondes pour la comparaison des dates
WAIT = 1 # Temps en seconde entre deux fichiers

class SyncerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Synchronisation Bidirectionnelle")

        # Variables pour les chemins
        self.org_dir = StringVar()
        self.dst_dir = StringVar()

        # Variable d'action
        self.GO = True

        # Création des cadres pour l'alignement
        path_frame = Frame(root)
        path_frame.pack(pady=5)

        # Alignement pour source
        Button(path_frame, text="Source", command=self.select_source).grid(row=0, column=0, padx=5)
        Entry(path_frame, textvariable=self.org_dir, width=50).grid(row=0, column=1)

        # Alignement pour destination
        Button(path_frame, text="Destination", command=self.select_destination).grid(row=1, column=0, padx=5)
        Entry(path_frame, textvariable=self.dst_dir, width=50).grid(row=1, column=1)

        # Création des boutons d'analyse et d'exécution dans un autre cadre pour l'alignement
        action_frame = Frame(root)
        action_frame.pack(pady=5)
        Button(action_frame, text="Analyse", command=self.run_analysis).grid(row=0, column=0, padx=5)
        Button(action_frame, text="Exécuter", command=self.execute_actions).grid(row=0, column=1, padx=5)
        Button(action_frame, text="Vider Analyse", command=self.clear_analysis).grid(row=0, column=2, padx=5)

        # Création de TreeView pour afficher les fichiers
        self.create_table_view()

        # Initialiser les bases de données et charger la configuration
        self.filters = {}  # Stockera les filtres en mémoire
        self.init_databases()
        self.init_filter_database()
        self.load_directories()

        # Variable pour le tooltip
        self.tooltip = None

        # Créer les menus contextuels
        self.create_context_menus()


    def create_table_view(self):
        """Créer un TreeView pour afficher les données sous forme de tableau"""
        frame = ttk.Frame(self.root)
        frame.pack(expand=True, fill="both")
        
        columns = ("org_dir", "org_name", "org_date", "action", "dst_dir", "dst_name", "dst_date")
        self.treeview = ttk.Treeview(frame, columns=columns, show="headings")

        # Configurer les colonnes
        self.treeview.heading("org_dir", text="Source")
        self.treeview.heading("org_name", text="Nom")
        self.treeview.heading("org_date", text="Date")
        self.treeview.heading("action", text="Action")
        self.treeview.heading("dst_dir", text="Destination")
        self.treeview.heading("dst_name", text="Nom")
        self.treeview.heading("dst_date", text="Date")

        # Ajuster la largeur des colonnes et centrer celle d'action
        self.treeview.column("org_dir", width=100)
        self.treeview.column("org_name", width=150)
        self.treeview.column("org_date", width=120)
        self.treeview.column("action", width=80, anchor="center")
        self.treeview.column("dst_dir", width=100)
        self.treeview.column("dst_name", width=150)
        self.treeview.column("dst_date", width=120)
        
        # Placement du TreeView et du Scrollbar dans le frame avec le grid
        self.treeview.grid(row=0, column=0, sticky="nsew")

        # Création des Scrollbars
        v_scrollbar = ttk.Scrollbar(frame, orient="vertical", command=self.treeview.yview)
        h_scrollbar = ttk.Scrollbar(frame, orient="horizontal", command=self.treeview.xview)
        self.treeview.configure(yscrollcommand=v_scrollbar.set, xscrollcommand=h_scrollbar.set)

        # Placement des Scrollbars
        v_scrollbar.grid(row=0, column=1, sticky="ns")
        h_scrollbar.grid(row=1, column=0, sticky="ew")

        # Configurer le redimensionnement dans le frame
        frame.grid_rowconfigure(0, weight=1)
        frame.grid_columnconfigure(0, weight=1)

        # Bind click droit pour menu contextuel
        self.treeview.bind("<Button-3>", self.show_context_menu)

        # Créer le menu contextuel
        self.context_menu_action = Menu(self.root, tearoff=0)
        actions = ["===", ">>>", "<<<", "==>", "<==", "--X", "X--", "/!\\", "-!-"]
        for action in actions:
            self.context_menu_action.add_command(label=action, command=lambda a=action: self.change_action(a))

        # Ajouter l'infobulle pour le chemin complet
        self.treeview.bind("<Motion>", self.show_tooltip)
        self.treeview.bind("<Leave>", self.hide_tooltip)
        
        # Définir les tags pour le style "-!-" (fichier exclus)
        self.treeview.tag_configure("-!-", foreground="white", background="#D3D3D3", font=("Helvetica", 10, "italic"))

    def clear_analysis(self):
        """Purge complètement la base de données syncer_analyse.db"""
        try:
            with sqlite3.connect(ANALYSE_DB) as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM sync_analysis")  # Suppression de toutes les données
                conn.commit()
            messagebox.showinfo("Succès", "La base de données d'analyse a été vidée.")
        except Exception as e:
            messagebox.showerror("Erreur", f"Erreur lors de la vidange de la base de données: {e}")

    def init_databases(self):
        """Initialise les bases de données si elles n'existent pas"""
        with sqlite3.connect(ANALYSE_DB) as conn:
            conn.execute('''CREATE TABLE IF NOT EXISTS sync_analysis (
                            path TEXT PRIMARY KEY,
                            time TIMESTAMP)''')
        
        with sqlite3.connect(CONFIG_DB) as conn:
            conn.execute('''CREATE TABLE IF NOT EXISTS sync_config (
                            key TEXT PRIMARY KEY,
                            value TEXT)''')


    def init_filter_database(self):
        """Initialise la base de données de filtres avec la table nécessaire."""
        with sqlite3.connect("syncer_filter.db") as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS filters (
                    type TEXT,
                    value TEXT,
                    UNIQUE(type, value)
                )
            """)
            conn.commit()


    def load_filters(self):
        """Charge les filtres depuis la base de données dans un dictionnaire."""
        self.filters = {'extension': set(), 'filename': set()}
        with sqlite3.connect("syncer_filter.db") as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT type, value FROM filters")
            for filter_type, value in cursor.fetchall():
                if filter_type in self.filters:
                    self.filters[filter_type].add(value)
        print("Filtres chargés :", self.filters)



    def add_filter(self, filter_type, value):
        """Ajoute un filtre dans la base de données, sauf s'il existe déjà."""
        with sqlite3.connect("syncer_filter.db") as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("INSERT INTO filters (type, value) VALUES (?, ?)", (filter_type, value))
                conn.commit()
                print(f"Filtre ajouté : {filter_type} - {value}")
            except sqlite3.IntegrityError:
                print(f"Le filtre {value} de type {filter_type} existe déjà.")

    def remove_filter(self, filter_type, value):
        """Supprime un filtre de la base de données."""
        with sqlite3.connect("syncer_filter.db") as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM filters WHERE type = ? AND value = ?", (filter_type, value))
            conn.commit()
            print(f"Filtre supprimé : {filter_type} - {value}")


    def filter_exists(self, filter_type, value):
        """Vérifie si un filtre existe dans la base de données."""
        with sqlite3.connect("syncer_filter.db") as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM filters WHERE type = ? AND value = ?", (filter_type, value))
            return cursor.fetchone() is not None




    def load_directories(self):
        """Charge les répertoires source et destination à partir de la base de données"""
        with sqlite3.connect(CONFIG_DB) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM sync_config WHERE key = ?", ("source",))
            org_path = cursor.fetchone()
            if org_path:
                self.org_dir.set(org_path[0])

            cursor.execute("SELECT value FROM sync_config WHERE key = ?", ("destination",))
            dst_path = cursor.fetchone()
            if dst_path:
                self.dst_dir.set(dst_path[0])

    def select_source(self):
        """Sélection du répertoire source"""
        directory = filedialog.askdirectory(title="Sélectionner le répertoire source")
        if directory:
            self.org_dir.set(directory)
            with sqlite3.connect(CONFIG_DB) as conn:
                conn.execute("REPLACE INTO sync_config (key, value) VALUES (?, ?)", ("source", directory))

    def select_destination(self):
        """Sélection du répertoire destination"""
        directory = filedialog.askdirectory(title="Sélectionner le répertoire destination")
        if directory:
            self.dst_dir.set(directory)
            with sqlite3.connect(CONFIG_DB) as conn:
                conn.execute("REPLACE INTO sync_config (key, value) VALUES (?, ?)", ("destination", directory))

    def run_analysis(self):
        """Lance l'analyse pour déterminer les actions de synchronisation"""
        if not self.org_dir.get() or not self.dst_dir.get():
            messagebox.showerror("Erreur", "Sélectionnez les répertoires source et destination.")
            return

        # Vider le TreeView avant l'analyse
        self.treeview.delete(*self.treeview.get_children())

        # Analyser et remplir les colonnes
        self.analyze_directory(self.org_dir.get(), self.dst_dir.get())



    def search_file_db(self, org_path, org_dir, dst_dir):
        """
        Vérifie si un fichier ou répertoire source existe dans le répertoire de destination
        en utilisant un chemin relatif basé sur le répertoire source.
        
        Args:
            org_path (str): Chemin complet du fichier ou répertoire dans le répertoire source.
            org_dir (str): Chemin du répertoire source.
            dst_dir (str): Chemin du répertoire de destination.

        Returns:
            bool: True si le fichier ou répertoire existe dans la destination, False sinon.
        """

        org_path = os.path.normpath(org_path)
        print(f"Origine :  {org_path}")
        org_dir = os.path.normpath(org_dir)
        print(f"Dir O :  {org_dir}")
        dst_dir = os.path.normpath(dst_dir)
        print(f"Dir D :  {dst_dir}")

        # Calculer le chemin relatif du fichier/répertoire à partir du répertoire source
        relative_path = os.path.relpath(org_path, org_dir)
        
        # Construire le chemin complet dans le répertoire de destination
        dst_full_path = os.path.join(dst_dir, relative_path)
        
        # Connexion à la base de données (ex: syncer.db)
        conn = sqlite3.connect('syncer_analyse.db')
        cursor = conn.cursor()
        
        # Requête SQL pour vérifier l'existence du chemin dans la destination
        query = """
        SELECT COUNT(*) FROM sync_analysis WHERE path = ?
        """
        cursor.execute(query, (dst_full_path,))
        result = cursor.fetchone()
        print(f"Recherche {dst_full_path}")
        print(f"Résultat {result[0]}")
        # Fermer la connexion
        conn.close()
        
        # Retourne True si le fichier existe, sinon False
        return result[0] > 0



    def check_db_mtime(self, path, mtime):
        """Vérifie si la date de modification d'un fichier dans la base de données correspond à la date actuelle.

        Args:
            path (str): Le chemin du fichier à vérifier.
            current_mtime (float): La date de modification actuelle du fichier.

        Returns:
            bool: True si la date de modification correspond, False sinon.
        """
        try:
            # Connexion à la base de données
            conn = sqlite3.connect('syncer_analyse.db')
            cursor = conn.cursor()

            # Vérification de la date de modification dans la base
            cursor.execute("SELECT time FROM sync_analysis WHERE path = ?", (path,))
            row = cursor.fetchone()

            if row:
                stored_mtime = row[0]
                # Comparaison des dates
                if stored_mtime == mtime :
                    print(f"OK - Ctrl mtime = {path} Store_mtime = {stored_mtime}")
                    return True
                else:
                    #print(f"Erreur - Ctrl mtime = {path} Store_mtime = {stored_mtime}")
                    return False
            else:
                # Le fichier n'est pas trouvé dans la base de données
                #print(f"Aucune date trouvée pour le fichier {path}")
                return False

        except sqlite3.Error as e:
            #print(f"Erreur lors de la vérification de la date dans la base de données : {e}")
            return False

        finally:
            conn.close()

    def analyze_directory(self, org_dir, dst_dir):
        self.load_filters()  # Charger les filtres avant de commencer l'analyse

        """Analyse et compare les répertoires source et destination"""
        org_dir = self.org_dir.get()
        dst_dir = self.dst_dir.get()

        # Set pour stocker les chemins relatifs ajoutés dans le TreeView
        seen_paths = set()

        # Analyser le répertoire source
        # On compare les dates de fichiers entre org et dst
        # On va aussi comparer par rapport à la base de donnée pour voir si confit
        # Ne s'applique uniquement que sur les fichiers !!!
        # Si la date du fichier plus à jour ne coincide pas avec la base de donnée, c'est normal
        # Si la destination à été modifiée entre temps (il y a conflit)
        # Permet aussi de détecter les suppression de répertoires
        # Si un répertoire ou un fichier existait en base de donnée, mais plus maintenant, c'est qu'il doit être effacé !
        for root, dirs, files in os.walk(org_dir):
            for org_name in dirs + files:
                dst_name = ""
                dst_mtime = None
                org_path = os.path.join(root, org_name)
                org_path = os.path.normpath(org_path)  # Normaliser ici
                org_path_isdir = os.path.isdir(org_path)
                org_mtime = datetime.fromtimestamp(os.path.getmtime(org_path))
                org_rel_path = os.path.relpath(org_path, org_dir)
                org_ext = os.path.splitext(org_name)[1]
                # Controle date en base
                org_ctrl_mtime = self.check_db_mtime(org_path, org_mtime.strftime('%y/%m/%d %H:%M:%S'))

                # Déterminer le chemin dans le dossier de destination
                dst_path = os.path.join(dst_dir, org_rel_path)
                dst_path = os.path.normpath(dst_path)  # Normaliser ici
                dst_path_isdir = os.path.isdir(dst_path)
                if os.path.exists(dst_path):
                    dst_name = os.path.basename(dst_path)
                    dst_mtime = datetime.fromtimestamp(os.path.getmtime(dst_path))
                    delta_seconds = abs((org_mtime - dst_mtime).total_seconds())
                    dst_ext = os.path.splitext(dst_name)[1]
                    # Controle date
                    dst_ctrl_mtime = self.check_db_mtime(dst_path, dst_mtime.strftime('%y/%m/%d %H:%M:%S'))

                    # Vérifier si le fichier ou l'extension doit être exclu
                    if dst_name in self.filters['filename'] or org_name in self.filters['filename'] or org_ext in self.filters['extension'] or dst_ext in self.filters['extension']:
                        action = "-!-"  # Pas de modification nécessaire
                    elif os.path.isdir(dst_path):
                        action = "==="  # Pas de modification nécessaire
                    elif delta_seconds <= DELTA:
                        action = "==="  # Pas de modification nécessaire
                    elif org_mtime > dst_mtime and dst_ctrl_mtime == True:
                        action = "==>"  # Copier de la source vers la destination
                    elif org_mtime < dst_mtime and org_ctrl_mtime == True:
                        action = "<=="  # Copier de la destination vers la source
                    elif dst_ctrl_mtime == False or org_ctrl_mtime == False:
                        action = "/!\\"  # erreur de coincidence
                        print(f"org_mtime = {org_mtime} dst_mtime = {dst_mtime}")
                elif org_name in self.filters['filename'] or org_ext in self.filters['extension']:
                    action = "-!-"  # Pas de modification nécessaire
                elif self.search_file_db(org_path, org_dir, dst_dir):
                    action = "X--"  # Supprime le fichier original
                else:
                    action = ">>>"  # Fichier à créer dans la destination
                    

                # Ajout dans le TreeView au fur et à mesure
                if org_rel_path not in seen_paths:
                   self.add_to_treeview(org_path, org_name, org_mtime, action, dst_path, dst_name, dst_mtime)
                   seen_paths.add(org_rel_path)  # Marquer le chemin comme traité

        # Analyser le répertoire source
        for root, dirs, files in os.walk(dst_dir):
            for dst_name in dirs + files:
                org_name = ""
                org_mtime = None
                dst_path = os.path.join(root, dst_name)
                dst_path = os.path.normpath(dst_path)  # Normaliser ici
                dst_path_isdir = os.path.isdir(dst_path)
                dst_mtime = datetime.fromtimestamp(os.path.getmtime(dst_path))
                dst_rel_path = os.path.relpath(dst_path, dst_dir)
                dst_ext = os.path.splitext(dst_name)[1]
                # Controle date en base
                dst_ctrl_mtime = self.check_db_mtime(dst_path, dst_mtime.strftime('%y/%m/%d %H:%M:%S'))


                # Déterminer le chemin dans le dossier de destination
                org_path = os.path.join(org_dir, dst_rel_path)
                org_path = os.path.normpath(org_path)  # Normaliser ici
                org_path_isdir = os.path.isdir(org_path)
                if os.path.exists(org_path):
                    org_name = os.path.basename(org_path)
                    org_mtime = datetime.fromtimestamp(os.path.getmtime(org_path))
                    delta_seconds = abs((dst_mtime - org_mtime).total_seconds())
                    org_ext = os.path.splitext(org_name)[1]
                    # Controle date en base
                    org_ctrl_mtime = self.check_db_mtime(org_path, org_mtime.strftime('%y/%m/%d %H:%M:%S'))

                    # Vérifier si le fichier ou l'extension doit être exclu
                    if dst_name in self.filters['filename'] or org_name in self.filters['filename'] or org_ext in self.filters['extension'] or dst_ext in self.filters['extension']:
                        action = "-!-"  # Pas de modification nécessaire
                    elif os.path.isdir(org_path):
                        action = "==="  # Pas de modification nécessaire
                    elif delta_seconds <= DELTA:
                        action = "==="  # Pas de modification nécessaire
                    elif dst_mtime > org_mtime and org_ctrl_mtime == True:
                        action = "<=="  # Copier de la source vers la destination
                    elif dst_mtime < org_mtime and dst_ctrl_mtime == True:
                        action = "==>"  # Copier de la destination vers la source
                    elif dst_ctrl_mtime == False or org_ctrl_mtime == False:
                        action = "/!\\"  # erreur de coincidence
                        #print(f"org_mtime = {org_mtime} dst_mtime = {dst_mtime}")

                elif dst_name in self.filters['filename'] or dst_ext in self.filters['extension']:
                    action = "-!-"  # Pas de modification nécessaire
                elif self.search_file_db(dst_path, dst_dir, org_dir):
                    action = "--X"  # Supprime le fichier destination
                else:                    
                    action = "<<<"  # Fichier à créer dans la destination

                    

                # Ajout dans le TreeView au fur et à mesure
                if dst_rel_path not in seen_paths:
                   self.add_to_treeview(org_path, org_name, org_mtime, action, dst_path, dst_name, dst_mtime)
                   seen_paths.add(dst_rel_path)  # Marquer le chemin comme traité


    def add_to_treeview(self, org_path, org_name, org_date, action, dst_path, dst_name, dst_date):
        """Ajoute une entrée au TreeView et met à jour la couleur de la colonne action uniquement"""
        item_id = self.treeview.insert("", "end", values=(org_path, org_name, org_date.strftime('%y/%m/%d %H:%M:%S') if org_date else "",
                                                          action, dst_path, dst_name, 
                                                          dst_date.strftime('%y/%m/%d %H:%M:%S') if dst_date else ""))

        # Configurer seulement la couleur du texte de la colonne Action
        self.set_action_color(item_id, action)
        self.root.update_idletasks()  # Permet la mise à jour au fur et à mesure

    def set_action_color(self, item_id, action):
        """Applique la couleur spécifique à la colonne Action en fonction de l'action sélectionnée"""
        colors = {
            "===": ("grey", "normal"),
            ">>>": ("green", "normal"), "<<<": ("green", "normal"), 
            "==>": ("green", "normal"), "<==": ("green", "normal"),
            "--X": ("red", "normal"), "--X": ("red", "normal"),
            "X--": ("red", "normal"), "X--": ("red", "normal"),  
            "/!\\": ("orange", "normal"),
            "-!-": ("white", "italic")  # Nouveau style pour fichier exclus
        }
        color, font_style = colors.get(action, ("black", "normal"))
        self.treeview.item(item_id, tags=(action,))
        self.treeview.tag_configure(action, foreground=color, font=("Helvetica", 10, font_style))

        if action == "-!-":  # Appliquer également le fond gris clair pour "-!-"
            self.treeview.tag_configure(action, background="#D3D3D3")

    def create_context_menus(self):
        """Crée les menus contextuels pour les colonnes Action et Nom"""
        # Menu contextuel pour la colonne Action
        self.context_menu_action = Menu(self.root, tearoff=0)
        actions = ["===", ">>>", "<<<", "==>", "<==", "--X", "X--", "/!\\", "-!-"]
        for action in actions:
            self.context_menu_action.add_command(label=action, command=lambda a=action: self.change_action(a))

        # Menu contextuel pour la colonne Nom
        self.context_menu_name = Menu(self.root, tearoff=0)
        self.context_menu_name.add_command(label="Exclure l'extension", command=self.exclude_extension)
        self.context_menu_name.add_command(label="Inclure l'extension", command=self.include_extension)
        self.context_menu_name.add_command(label="Exclure le nom de fichier", command=self.exclude_filename)
        self.context_menu_name.add_command(label="Inclure le nom de fichier", command=self.include_filename)



    def show_context_menu(self, event):
        """Affiche le menu contextuel sur clic droit pour les colonnes Action et Nom"""
        self.load_filters()  # Charger les filtres avant de commencer l'analyse

        row_id = self.treeview.identify_row(event.y)
        col = self.treeview.identify_column(event.x)
        
        # Vérifier si le clic droit est sur la colonne Action (index #4)
        if col == '#4' and row_id:
            self.treeview.selection_set(row_id)
            self.context_menu_action.post(event.x_root, event.y_root)
        
        # Vérifier si le clic droit est sur les colonnes Nom (index #2 pour org_name et #6 pour dst_name)
        elif col in ('#2', '#6') and row_id:
            self.treeview.selection_set(row_id)
            
            # Déterminer la colonne cliquée et obtenir le bon nom de fichier
            if col == '#2':
                filename = self.treeview.set(row_id, "org_name")
                context_column = "org_name"
            else:
                filename = self.treeview.set(row_id, "dst_name")
                context_column = "dst_name"
            
            # Ne rien faire si le nom de fichier est vide
            if not filename:
                return
            
            extension = os.path.splitext(filename)[1]
            

            #if dst_name in self.filters['filename'] or extension in self.filters['extension']:

            # Vérifier si c'est un fichier ou un répertoire (les répertoires n'ont pas d'extension)
            is_directory = not extension
            
            # Vider le menu contextuel
            self.context_menu_name.delete(0, "end")
            
            # Ajouter les options de menu selon le type d'élément
            if not is_directory:
                if extension in self.filters['extension']:
                    self.context_menu_name.add_command(
                        label=f"Inclure l'extension : {extension}", 
                        command=lambda: self.include_extension(extension, context_column)
                    )
                else:
                    self.context_menu_name.add_command(
                        label=f"Exclure l'extension : {extension}", 
                        command=lambda: self.exclude_extension(extension, context_column)
                    )

            # Ajouter les options d'inclusion/exclusion par nom pour tous les éléments
            if filename in self.filters['filename']:
                print(f"Le nom de fichier {filename} est déjà dans les filtres.")
                self.context_menu_name.add_command(
                    label=f"Inclure le nom de fichier : {filename}", 
                    command=lambda: self.include_filename(filename, context_column)
                )
            else:
                print(f"Le nom de fichier {filename} n'est pas dans les filtres.")
                self.context_menu_name.add_command(
                    label=f"Exclure le nom de fichier : {filename}", 
                    command=lambda: self.exclude_filename(filename, context_column)
                )
            
            # Afficher le menu contextuel de la colonne Nom
            self.context_menu_name.post(event.x_root, event.y_root)
        else:
            # Annuler le menu contextuel s'il n'est pas dans les colonnes Action ou Nom
            self.context_menu_action.unpost()
            self.context_menu_name.unpost()

    # Modifications dans les méthodes pour utiliser la bonne colonne

    def exclude_extension(self, extension, column):
        """Exclure l'extension du fichier sélectionné dans la colonne spécifiée"""
        selected_item = self.treeview.selection()[0]
        filename = self.treeview.set(selected_item, column)
        extension = os.path.splitext(filename)[1]
        # Code pour ajouter l'extension à exclure dans la base de données
        if not self.filter_exists("extension", extension):
            self.add_filter("extension", extension)
            print(f"Extension exclue pour {column} : {extension}")


    def include_extension(self, extension, column):
        """Inclure l'extension du fichier sélectionné dans la colonne spécifiée"""
        selected_item = self.treeview.selection()[0]
        filename = self.treeview.set(selected_item, column)
        extension = os.path.splitext(filename)[1]
        # Code pour inclure l'extension dans la base de données
        print(f"Extension incluse pour {column} : {extension}")
        if self.filter_exists("extension", extension):
            self.remove_filter("extension", extension)


    def exclude_filename(self, filename, column):
        """Exclure le nom de fichier sélectionné dans la colonne spécifiée"""
        selected_item = self.treeview.selection()[0]
        filename = self.treeview.set(selected_item, column)
        # Code pour ajouter le nom de fichier à exclure dans la base de données
        if not self.filter_exists("filename", filename):
            self.add_filter("filename", filename)
            print(f"Nom de fichier exclu pour {column} : {filename}")


    def include_filename(self, filename, column):
        """Inclure le nom de fichier sélectionné dans la colonne spécifiée"""
        selected_item = self.treeview.selection()[0]
        filename = self.treeview.set(selected_item, column)
        # Code pour inclure le nom de fichier dans la base de données
        if self.filter_exists("filename", filename):
            self.remove_filter("filename", filename)
            print(f"Nom de fichier inclus pour {column} : {filename}")



    def change_action(self, new_action):
        """Change l'action de l'élément sélectionné dans le TreeView"""
        selected_items = self.treeview.selection()
        if not selected_items:
            print("Aucun élément sélectionné.")
            return  # Sort de la fonction si aucun élément n'est sélectionné

        selected_item = selected_items[0]
        current_values = self.treeview.item(selected_item, "values")

        # Met à jour la valeur de l'action
        new_values = list(current_values)
        new_values[3] = new_action  # Suppose que l'action est à l'index 3
        self.treeview.item(selected_item, values=new_values)

        # Met à jour la couleur de la colonne action
        self.set_action_color(selected_item, new_action)




    def show_tooltip(self, event):
        """Affiche un tooltip avec le chemin complet lorsque la souris est sur un répertoire source ou destination"""
        if self.tooltip:  # Si un tooltip existe déjà, le détruire
            self.tooltip.destroy()

        row_id = self.treeview.identify_row(event.y)
        col = self.treeview.identify_column(event.x)
        if row_id and col in ('#1', '#5'):  # Colonnes Source Directory ou Destination Directory
            path = self.treeview.set(row_id, col)
            # Crée un popup temporaire pour afficher le chemin complet
            self.tooltip = Toplevel(self.root)
            self.tooltip.overrideredirect(True)
            self.tooltip.geometry(f"+{event.x_root + 20}+{event.y_root + 20}")
            Label(self.tooltip, text=path, background="yellow").pack()

            # Faire disparaître le tooltip après 1 seconde
            self.tooltip.after(1000, self.tooltip.destroy)

    def hide_tooltip(self, event):
        """Cache le tooltip lorsque la souris quitte la zone de TreeView"""
        if self.tooltip:
            self.tooltip.destroy()
            self.tooltip = None

    def execute_actions(self):
        """Exécute les actions définies dans le TreeView."""
        with sqlite3.connect(ANALYSE_DB) as conn:
            cursor = conn.cursor()

        while self.treeview.get_children():  # Tant qu'il y a des éléments
            item = self.treeview.item(self.treeview.get_children()[0])  # Toujours prendre le premier enfant
            org_path = item['values'][0]  # Chemin source
            org_mtime = item['values'][2]  # Date source
            action = item['values'][3]  # Action
            dst_path = item['values'][4]  # Chemin destination
            dst_mtime = item['values'][6]  # Date destination
            
            # Normaliser les chemins pour éviter les problèmes de slash
            org_path = os.path.normpath(org_path)
            dst_path = os.path.normpath(dst_path)

            # Afficher l'action dans la console
            print(f"Origine: {org_path}, Action: {action}, Chemin destination: {dst_path}")

            # Vérifier les dates de fichiers
            if os.path.exists(org_path) and os.path.exists(dst_path):
                current_org_mtime = datetime.fromtimestamp(os.path.getmtime(org_path)).strftime('%y/%m/%d %H:%M:%S')
                current_dst_mtime = datetime.fromtimestamp(os.path.getmtime(dst_path)).strftime('%y/%m/%d %H:%M:%S')
                
                if current_org_mtime != org_mtime or current_dst_mtime != dst_mtime:
                    print(f"Changement détecté dans les dates des fichiers: {org_path} ou {dst_path}")
                    self.treeview.delete(self.treeview.get_children()[0])  # Supprimer l'élément malgré tout
                    self.treeview.update_idletasks()  # Rafraîchir l'affichage
                    continue  # Passer à l'itération suivante si les dates ont changé
            
            # Exécuter l'action selon le type d'action
            if action == "===":
                #print(f"Copie de {org_path} vers {dst_path}")
                # Supprimer les anciens enregistrements pour le fichier source et destination
                cursor.execute("DELETE FROM sync_analysis WHERE path = ? OR path = ?", (org_path, dst_path))
                # Ajouter les nouveaux enregistrements pour le fichier source et destination
                cursor.execute("INSERT INTO sync_analysis (path, time) VALUES (?, ?)", (org_path, current_org_mtime))
                cursor.execute("INSERT INTO sync_analysis (path, time) VALUES (?, ?)", (dst_path, current_dst_mtime))
                conn.commit()

            elif action == "==>":
                #print(f"Copie de {org_path} vers {dst_path}")
                # Supprimer les anciens enregistrements pour le fichier source et destination
                cursor.execute("DELETE FROM sync_analysis WHERE path = ? OR path = ?", (org_path, dst_path))
                if self.GO:
                    shutil.copy2(org_path, dst_path)
                    time.sleep(WAIT)
                # Ajouter les nouveaux enregistrements pour le fichier source et destination
                cursor.execute("INSERT INTO sync_analysis (path, time) VALUES (?, ?)", (org_path, current_org_mtime))
                cursor.execute("INSERT INTO sync_analysis (path, time) VALUES (?, ?)", (dst_path, current_dst_mtime))
                conn.commit()

            elif action == "<==":
                #print(f"Copie de {dst_path} vers {org_path}")
                # Supprimer les anciens enregistrements pour le fichier source et destination
                cursor.execute("DELETE FROM sync_analysis WHERE path = ? OR path = ?", (org_path, dst_path))
                if self.GO:
                    shutil.copy2(dst_path, org_path)
                    time.sleep(WAIT)
                # Ajouter les nouveaux enregistrements pour le fichier source et destination
                cursor.execute("INSERT INTO sync_analysis (path, time) VALUES (?, ?)", (org_path, current_org_mtime))
                cursor.execute("INSERT INTO sync_analysis (path, time) VALUES (?, ?)", (dst_path, current_dst_mtime))
                conn.commit()

            elif action == ">>>" and os.path.isdir(org_path): # copie de répertoire
                #print(f"Création de {dst_path}")
                # Supprimer les anciens enregistrements pour le fichier source et destination
                cursor.execute("DELETE FROM sync_analysis WHERE path = ? OR path = ?", (org_path, dst_path))
                if self.GO:
                    os.makedirs(dst_path, exist_ok=True)
                    time.sleep(WAIT)
                cursor.execute("INSERT INTO sync_analysis (path, time) VALUES (?, ?)", (org_path, current_org_mtime))
                cursor.execute("INSERT INTO sync_analysis (path, time) VALUES (?, ?)", (dst_path, current_dst_mtime))
                conn.commit()

            elif action == ">>>" and not os.path.isdir(org_path): # copie de fichier
                #print(f"Création de {dst_path}")
                # Supprimer les anciens enregistrements pour le fichier source et destination
                cursor.execute("DELETE FROM sync_analysis WHERE path = ? OR path = ?", (org_path, dst_path))
                if self.GO:
                    shutil.copy2(org_path, dst_path)
                    time.sleep(WAIT)
                cursor.execute("INSERT INTO sync_analysis (path, time) VALUES (?, ?)", (org_path, current_org_mtime))
                cursor.execute("INSERT INTO sync_analysis (path, time) VALUES (?, ?)", (dst_path, current_dst_mtime))
                conn.commit()

            elif action == "<<<" and os.path.isdir(dst_path): # copie de répertoire
                #print(f"Création de {org_path}")
                # Supprimer les anciens enregistrements pour le fichier source et destination
                cursor.execute("DELETE FROM sync_analysis WHERE path = ? OR path = ?", (org_path, dst_path))
                if self.GO:
                    os.makedirs(org_path, exist_ok=True)
                    time.sleep(WAIT)
                cursor.execute("INSERT INTO sync_analysis (path, time) VALUES (?, ?)", (org_path, current_org_mtime))
                cursor.execute("INSERT INTO sync_analysis (path, time) VALUES (?, ?)", (dst_path, current_dst_mtime))
                conn.commit()

            elif action == "<<<" and not os.path.isdir(dst_path): # copie de fichier
                #print(f"Création de {org_path}")
                # Supprimer les anciens enregistrements pour le fichier source et destination
                cursor.execute("DELETE FROM sync_analysis WHERE path = ? OR path = ?", (org_path, dst_path))
                if self.GO:
                    shutil.copy2(dst_path, org_path)
                    time.sleep(WAIT)
                cursor.execute("INSERT INTO sync_analysis (path, time) VALUES (?, ?)", (org_path, current_org_mtime))
                cursor.execute("INSERT INTO sync_analysis (path, time) VALUES (?, ?)", (dst_path, current_dst_mtime))
                conn.commit()

            elif action == "--X" and os.path.isdir(dst_path): # supression de répertoire
                #print(f"Suppression de {dst_path}")
                if self.GO:
                    shutil.rmtree(dst_path)
                    time.sleep(WAIT)
                # Supprimer les anciens enregistrements pour le fichier source et destination
                cursor.execute("DELETE FROM sync_analysis WHERE path = ? OR path = ?", (org_path, dst_path))
                conn.commit()

            elif action == "--X" and not os.path.isdir(dst_path): # supression de fichier
                #print(f"Suppression de {dst_path}")
                if self.GO:
                    os.remove(dst_path)
                    time.sleep(WAIT)
                # Supprimer les anciens enregistrements pour le fichier source et destination
                cursor.execute("DELETE FROM sync_analysis WHERE path = ? OR path = ?", (org_path, dst_path))
                conn.commit()

            elif action == "X--" and os.path.isdir(org_path): # supression de répertoire
                #print(f"Suppression de {org_path}")
                if self.GO:
                    shutil.rmtree(org_path)
                    time.sleep(WAIT)
                # Supprimer les anciens enregistrements pour le fichier source et destination
                cursor.execute("DELETE FROM sync_analysis WHERE path = ? OR path = ?", (org_path, dst_path))
                conn.commit()

            elif action == "X--" and not os.path.isdir(dst_path): # supression de fichier
                #print(f"Suppression de {org_path}")
                if self.GO:
                    os.remove(org_path)
                    time.sleep(WAIT)
                # Supprimer les anciens enregistrements pour le fichier source et destination
                cursor.execute("DELETE FROM sync_analysis WHERE path = ? OR path = ?", (org_path, dst_path))
                conn.commit()

            elif action == "-!-":
                print(f"Exclusion de {org_path} ou {dst_path}")

            # Supprimer la ligne au fur et à mesure
            self.treeview.delete(self.treeview.get_children()[0])  # Supprime toujours le premier enfant
            self.treeview.update_idletasks()  # Rafraîchir l'affichage




# Lancer l'application
root = Tk()
app = SyncerApp(root)
root.mainloop()
