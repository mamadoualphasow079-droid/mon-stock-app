import streamlit as st
import pandas as pd
import psycopg2
import os

# --- INITIALISATION DE L'ÉTAT ET DE LA BASE DE DONNÉES ---

# 1. Initialiser le panier d'achats
if 'cart' not in st.session_state:
    st.session_state['cart'] = []

# 2. Initialiser la structure de la page
st.set_page_config(page_title="Gestion Stock & Crédit", layout="wide")
st.title("🛒 Gestion de Stock et Crédit Client")

# --- FONCTIONS DE BASE DE DONNÉES ---

def get_db_connection():
    try:
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
        # st.error(f"Erreur d'exécution de la requête : {e}")
        if conn: conn.close()
        return [] if fetch else None

def init_db_structure():
    """Crée les tables et colonnes si elles n'existent pas (Méthode de rattrapage)."""
    # Création des tables
    exec_query("""CREATE TABLE IF NOT EXISTS produits (id SERIAL PRIMARY KEY, nom TEXT NOT NULL, prix REAL, quantite INTEGER)""")
    exec_query("""CREATE TABLE IF NOT EXISTS ventes (id SERIAL PRIMARY KEY, produit_id INTEGER REFERENCES produits(id), quantite INTEGER, date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
    exec_query("""CREATE TABLE IF NOT EXISTS clients (id SERIAL PRIMARY KEY, nom TEXT NOT NULL, adresse TEXT, plafond_credit REAL DEFAULT 0.0, solde_du REAL DEFAULT 0.0)""")

    # Ajout des colonnes de liaison
    exec_query("ALTER TABLE ventes ADD COLUMN client_id INTEGER REFERENCES clients(id)")
    exec_query("ALTER TABLE ventes ADD COLUMN montant_credit REAL DEFAULT 0.0")

# Initialisation de la base de données
if 'db_structure_ok' not in st.session_state:
    init_db_structure()
    st.session_state['db_structure_ok'] = True
    st.success("Configuration de la base de données terminée (clients, crédit, historique)!")


# --- FONCTIONS DU PANIER ---

def clear_cart():
    st.session_state['cart'] = []

def add_to_cart_callback(pid, nom, prix, stock, qty):
    if qty <= 0:
        st.warning("Veuillez entrer une quantité valide.")
        return
    if qty > stock:
        st.error(f"Stock insuffisant. Seulement {stock} disponibles.")
        return
        
    item_total = prix * qty
    
    # Ajouter l'article au panier
    st.session_state['cart'].append({
        'id': pid,
        'nom': nom,
        'prix_u': prix,
        'quantite': qty,
        'total': item_total,
        'stock_dispo': stock
    })
    
    st.success(f"➕ {qty} x {nom} (Total: {item_total:.2f} €) ajouté au panier.")


# --- Menu Principal ---
menu = st.sidebar.radio("Menu", ["Vendre", "Stock", "Clients & Crédit", "Historique Ventes", "Ajouter Produit"])

# --- SECTION VENDRE (MISE À JOUR MAJEURE) ---

if menu == "Vendre":
    st.header("Enregistrer une Vente (Panier d'Achat)")
    
    # Séparer l'interface en deux colonnes
    col1, col2 = st.columns([1, 1])

    with col1:
        st.subheader("1. Ajouter des articles au panier")
        
        # Récupérer les produits
        produits_db = exec_query("SELECT id, nom, prix, quantite FROM produits WHERE quantite > 0 ORDER BY nom", fetch=True)
        option_produit = {p[1]: (p[0], p[2], p[3]) for p in produits_db} 
        
        with st.form("form_add_to_cart", clear_on_submit=True):
            choix_produit = st.selectbox("Produit", list(option_produit.keys()) if option_produit else [], key="sel_prod_add")
            
            if choix_produit:
                pid, prix, stock_actuel = option_produit[choix_produit]
                st.info(f"Prix unitaire: {prix} € | Stock disponible: {stock_actuel}")
                
                # Quantité à ajouter
                qty_add = st.number_input(
                    "Quantité à ajouter", 
                    min_value=1, 
                    max_value=stock_actuel, 
                    step=1, 
                    value=1, 
                    key="qty_add_input"
                )
                
                # Bouton d'ajout
                if st.form_submit_button("🛒 Ajouter au Panier"):
                    add_to_cart_callback(pid, choix_produit, prix, stock_actuel, qty_add)
    
    with col2:
        st.subheader("2. Panier et Validation")
        
        # Afficher le panier
        if st.session_state['cart']:
            df_cart = pd.DataFrame(st.session_state['cart'])
            
            # Afficher le panier sans colonnes techniques
            st.dataframe(
                df_cart[['nom', 'quantite', 'prix_u', 'total']],
                column_config={
                    "nom": "Produit",
                    "quantite": "Qté",
                    "prix_u": st.column_config.NumberColumn("Prix U.", format="%.2f €"),
                    "total": st.column_config.NumberColumn("Total", format="%.2f €"),
                },
                hide_index=True,
                use_container_width=True
            )
            
            total_panier = df_cart['total'].sum()
            st.metric("TOTAL DE LA VENTE", value=f"{total_panier:.2f} €")
            
            st.button("Vider le panier", on_click=clear_cart)
            
            # --- FORMULAIRE DE VALIDATION FINALE ---
            
            st.markdown("---")
            st.markdown("##### Finalisation de la Vente")
            
            clients_db = exec_query("SELECT id, nom, solde_du, plafond_credit FROM clients", fetch=True)
            option_client = {c[1]: (c[0], c[2], c[3]) for c in clients_db} 
            client_choices = ["Vente comptant (Payé immédiatement)"] + list(option_client.keys())
            
            with st.form("form_finalize_sale"):
                choix_client = st.selectbox("Client ou Type de Vente", client_choices, key="sel_client_final")
                
                if st.form_submit_button("✅ Valider la Vente Finale"):
                    
                    # Logique de Crédit et Vérification
                    client_id = None
                    montant_credit = 0.0
                    
                    if choix_client != "Vente comptant (Payé immédiatement)":
                        cid, solde_du, plafond = option_client[choix_client]
                        client_id = cid
                        
                        nouveau_solde = solde_du + total_panier
                        if nouveau_solde > plafond:
                            st.error(f"❌ CRÉDIT REFUSÉ ! Le solde de {nouveau_solde:.2f} € dépasse le plafond de {plafond:.2f} €.")
                            st.stop()
                        
                        montant_credit = total_panier
                        
                        # Mise à jour du solde dû du client
                        sql_update_solde = "UPDATE clients SET solde_du = solde_du + %s WHERE id = %s"
                        exec_query(sql_update_solde, (total_panier, client_id))
                    
                    # Enregistrement et Stock
                    for item in st.session_state['cart']:
                        # Enregistrement de la Vente
                        sql_vente = "INSERT INTO ventes (produit_id, quantite, client_id, montant_credit) VALUES (%s, %s, %s, %s)"
                        exec_query(sql_vente, (item['id'], item['quantite'], client_id, montant_credit if item == st.session_state['cart'][0] else 0.0)) # Seulement le premier article porte le montant total du crédit pour ne pas dupliquer la somme
                        
                        # Mise à jour du Stock
                        sql_stock = "UPDATE produits SET quantite = quantite - %s WHERE id = %s"
                        exec_query(sql_stock, (item['quantite'], item['id']))
                    
                    st.success(f"🥳 Vente de {len(st.session_state['cart'])} article(s) enregistrée. Total: {total_panier:.2f} €.")
                    clear_cart() # Vider le panier après validation
                    st.rerun() # Rafraichir
        
        else:
            st.info("Le panier est vide. Veuillez ajouter des articles à gauche.")


# --- SECTIONS SECONDAIRES (Non modifiées) ---

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

elif menu == "Clients & Crédit":
    st.header("Gestion des Clients et Plafonds de Crédit")
    with st.expander("➕ Ajouter un nouveau client"):
        with st.form("ajout_client_form"):
            nom = st.text_input("Nom du Client")
            adresse = st.text_input("Adresse")
            plafond_credit = st.number_input("Plafond de Crédit Max Autorisé", min_value=0.0, step=500.0, value=0.0)
            
            if st.form_submit_button("Créer le Client"):
                sql = "INSERT INTO clients (nom, adresse, plafond_credit) VALUES (%s, %s, %s)"
                exec_query(sql, (nom, adresse, plafond_credit))
                st.success(f"👤 Client '{nom}' créé avec un plafond de {plafond_credit} €")

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
