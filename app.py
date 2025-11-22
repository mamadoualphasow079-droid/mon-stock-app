import streamlit as st
import pandas as pd
import psycopg2
import os

# --- Configuration et Connexion DB ---
st.set_page_config(page_title="Gestion Stock & Crédit", layout="wide")
st.title("💳 Gestion de Stock et Crédit Client")

def get_db_connection():
    try:
        # Récupère l'URL secrète depuis Render
        url = os.environ.get('DATABASE_URL')
        conn = psycopg2.connect(url)
        return conn
    except Exception as e:
        # st.error(f"Erreur de connexion à la base de données : {e}")
        return None

def exec_query(sql, params=None, fetch=False):
    """Exécute une requête et retourne les résultats si fetch est True."""
    conn = get_db_connection()
    if conn is None:
        return [] if fetch else None
    
    try:
        c = conn.cursor()
        c.execute(sql, params or ())
        if fetch:
            result = c.fetchall()
            conn.close()
            return result
        conn.commit()
        conn.close()
    except psycopg2.errors.DuplicateColumn:
        # Ignorer l'erreur si une colonne existe déjà, c'est ce qu'on veut.
        if conn: conn.close()
        pass 
    except Exception as e:
        st.error(f"Erreur d'exécution de la requête : {e}")
        if conn: conn.close()
        return [] if fetch else None

def init_db_structure():
    """
    Crée les tables et colonnes si elles n'existent pas (Méthode de rattrapage).
    """
    # 1. Création des tables Produits et Ventes (pour être sûr)
    exec_query("""
        CREATE TABLE IF NOT EXISTS produits (
            id SERIAL PRIMARY KEY, 
            nom TEXT NOT NULL, 
            prix REAL, 
            quantite INTEGER
        )
    """)
    exec_query("""
        CREATE TABLE IF NOT EXISTS ventes (
            id SERIAL PRIMARY KEY, 
            produit_id INTEGER REFERENCES produits(id), 
            quantite INTEGER, 
            date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # 2. Création de la table Clients
    exec_query("""
        CREATE TABLE IF NOT EXISTS clients (
            id SERIAL PRIMARY KEY,
            nom TEXT NOT NULL,
            adresse TEXT,
            plafond_credit REAL DEFAULT 0.0,
            solde_du REAL DEFAULT 0.0
        )
    """)

    # 3. Ajout des colonnes de liaison dans la table Ventes (avec gestion d'erreur)
    # Nous utilisons la gestion d'erreur intégrée dans exec_query pour les ALTER TABLE.
    exec_query("ALTER TABLE ventes ADD COLUMN client_id INTEGER REFERENCES clients(id)")
    exec_query("ALTER TABLE ventes ADD COLUMN montant_credit REAL DEFAULT 0.0")

# --- INITIALISATION AU DÉMARRAGE ---
if 'db_structure_ok' not in st.session_state:
    init_db_structure()
    st.session_state['db_structure_ok'] = True
    st.success("Configuration de la base de données terminée (clients, crédit, historique)!")


# --- Menu Principal ---
menu = st.sidebar.radio("Menu", ["Vendre", "Stock", "Clients & Crédit", "Historique Ventes", "Ajouter Produit"])

# --- SECTION 1 : GESTION CLIENTS & CRÉDIT ---

if menu == "Clients & Crédit":
    st.header("Gestion des Clients et Plafonds de Crédit")

    # Onglet Ajouter Client
    with st.expander("➕ Ajouter un nouveau client"):
        with st.form("ajout_client_form"):
            nom = st.text_input("Nom du Client")
            adresse = st.text_input("Adresse")
            plafond_credit = st.number_input("Plafond de Crédit Max Autorisé", min_value=0.0, step=500.0, value=0.0)
            
            if st.form_submit_button("Créer le Client"):
                sql = "INSERT INTO clients (nom, adresse, plafond_credit) VALUES (%s, %s, %s)"
                exec_query(sql, (nom, adresse, plafond_credit))
                st.success(f"👤 Client '{nom}' créé avec un plafond de {plafond_credit} €")

    # Onglet Afficher Clients
    st.subheader("Liste et Détails des Clients")
    sql = "SELECT id, nom, adresse, plafond_credit, solde_du FROM clients ORDER BY solde_du DESC"
    df_clients = pd.read_sql(sql, get_db_connection())

    def color_du(val):
        color = 'red' if val > 0 else 'black'
        return f'color: {color}'

    st.dataframe(
        df_clients.style.applymap(color_du, subset=['solde_du']),
        column_config={
            "plafond_credit": st.column_config.NumberColumn("Plafond Crédit (€)", format="%.2f"),
            "solde_du": st.column_config.NumberColumn("Solde Dû (€)", format="%.2f")
        },
        use_container_width=True
    )
    
# --- SECTION 2 : HISTORIQUE DES VENTES ---

elif menu == "Historique Ventes":
    st.header("Historique de Toutes les Transactions")

    sql = """
    SELECT 
        v.id AS "ID Vente",
        p.nom AS "Produit",
        v.quantite AS "Qté",
        c.nom AS "Client",
        v.montant_credit AS "Crédit (€)",
        v.date AS "Date"
    FROM ventes v
    JOIN produits p ON v.produit_id = p.id
    LEFT JOIN clients c ON v.client_id = c.id
    ORDER BY v.date DESC
    LIMIT 100
    """
    df_history = pd.read_sql(sql, get_db_connection())
    st.dataframe(df_history, use_container_width=True)

# --- SECTION 3 : VENDRE (Logique principale) ---

elif menu == "Vendre":
    st.header("Enregistrer une Vente")

    # Récupérer les données
    produits_db = exec_query("SELECT id, nom, prix, quantite FROM produits", fetch=True)
    option_produit = {p[1]: (p[0], p[2], p[3]) for p in produits_db} 
    
    clients_db = exec_query("SELECT id, nom, solde_du, plafond_credit FROM clients", fetch=True)
    option_client = {c[1]: (c[0], c[2], c[3]) for c in clients_db} 
    client_choices = ["Vente comptant (Payé immédiatement)"] + list(option_client.keys())

    # Formulaire de vente
    with st.form("form_vente"):
        choix_produit = st.selectbox("1. Choisir le produit", list(option_produit.keys()) if option_produit else [])
        choix_client = st.selectbox("2. Client ou Type de Vente", client_choices)
        
        total_vente = 0
        if choix_produit:
            pid, prix, stock_actuel = option_produit[choix_produit]
            st.info(f"Prix unitaire: {prix} € | Stock disponible: {stock_actuel}")
            qty_vendu = st.number_input("3. Quantité vendue", min_value=1, max_value=stock_actuel, step=1, key="qty_vendu")
            total_vente = prix * qty_vendu
            st.subheader(f"Total à payer : {total_vente:.2f} €")
        
        if st.form_submit_button("Valider la Transaction"):
            if not choix_produit:
                st.error("Veuillez sélectionner un produit.")
                st.stop()
                
            client_id = None
            montant_credit = 0.0
            
            # Gestion Vente à Crédit
            if choix_client != "Vente comptant (Payé immédiatement)":
                cid, solde_du, plafond = option_client[choix_client]
                client_id = cid
                
                nouveau_solde = solde_du + total_vente
                if nouveau_solde > plafond:
                    st.error(f"❌ Crédit refusé ! Le solde de {nouveau_solde:.2f} € dépasse le plafond de {plafond:.2f} €.")
                    st.stop()
                
                montant_credit = total_vente
                
                # Mise à jour du solde dû du client
                sql_update_solde = "UPDATE clients SET solde_du = solde_du + %s WHERE id = %s"
                exec_query(sql_update_solde, (total_vente, client_id))
            
            # Enregistrement de la Vente
            sql_vente = "INSERT INTO ventes (produit_id, quantite, client_id, montant_credit) VALUES (%s, %s, %s, %s)"
            exec_query(sql_vente, (pid, qty_vendu, client_id, montant_credit))

            # Mise à jour du Stock
            sql_stock = "UPDATE produits SET quantite = quantite - %s WHERE id = %s"
            exec_query(sql_stock, (qty_vendu, pid))
            
            st.success(f"💰 Transaction enregistrée. Stock mis à jour.")
            st.rerun() 

# --- SECTION 4 : STOCK ET AJOUT PRODUIT (Reste du menu) ---

elif menu == "Stock":
    st.header("État du Stock Actuel")
    sql = "SELECT id, nom, prix, quantite FROM produits ORDER BY id"
    df = pd.read_sql(sql, get_db_connection())
    st.dataframe(df, use_container_width=True)

elif menu == "Ajouter Produit":
    st.header("Nouveau Produit")
    with st.form("ajout_produit_form_simple"):
        nom = st.text_input("Nom du produit")
        prix = st.number_input("Prix de vente", min_value=0.0, step=100.0)
        qty = st.number_input("Quantité initiale", min_value=1, step=1)
        
        if st.form_submit_button("Ajouter le Produit"):
            sql = "INSERT INTO produits (nom, prix, quantite) VALUES (%s, %s, %s)"
            exec_query(sql, (nom, prix, qty))
            st.success(f"✅ Produit '{nom}' ajouté !")
