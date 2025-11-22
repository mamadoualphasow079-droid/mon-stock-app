import streamlit as st
import pandas as pd
import psycopg2
import os

# --- INITIALISATION DE L'ÉTAT ET DE LA BASE DE DONNÉES ---

if 'cart_credit' not in st.session_state:
    st.session_state['cart_credit'] = []
if 'cart_cash' not in st.session_state:
    st.session_state['cart_cash'] = []

st.set_page_config(page_title="Gestion Stock & Crédit", layout="wide")
st.title("🛒 Gestion de Stock, Crédit et Paiements")

# --- FONCTIONS DE BASE DE DONNÉES (RÉ-INCLUSES POUR LA VÉRIFICATION) ---

def get_db_connection():
    try:
        # Assurez-vous que la variable d'environnement DATABASE_URL est bien configurée sur Render/GitHub
        url = os.environ.get('DATABASE_URL')
        if not url:
            st.error("DATABASE_URL non configuré. Veuillez vérifier les secrets de l'application.")
            return None
        conn = psycopg2.connect(url)
        return conn
    except Exception as e:
        st.error(f"Erreur de connexion DB: {e}")
        return None

def exec_query(sql, params=None, fetch=False):
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
        if conn: conn.close()
        pass 
    except Exception as e:
        if conn: conn.close()
        st.error(f"Erreur d'exécution SQL: {e}")
        return [] if fetch else None

def init_db_structure():
    """Crée les tables et colonnes si elles n'existent pas."""
    # Création des tables
    exec_query("""CREATE TABLE IF NOT EXISTS produits (id SERIAL PRIMARY KEY, nom TEXT NOT NULL, prix REAL, quantite INTEGER)""")
    exec_query("""CREATE TABLE IF NOT EXISTS ventes (id SERIAL PRIMARY KEY, produit_id INTEGER REFERENCES produits(id), quantite INTEGER, date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
    exec_query("""CREATE TABLE IF NOT EXISTS clients (id SERIAL PRIMARY KEY, nom TEXT NOT NULL, adresse TEXT, plafond_credit REAL DEFAULT 0.0, solde_du REAL DEFAULT 0.0)""")
    exec_query("""CREATE TABLE IF NOT EXISTS paiements (id SERIAL PRIMARY KEY, client_id INTEGER REFERENCES clients(id) NOT NULL, montant REAL NOT NULL, date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")

    # Ajout des colonnes si elles manquent (pour la compatibilité)
    try:
        exec_query("ALTER TABLE ventes ADD COLUMN client_id INTEGER REFERENCES clients(id)")
    except: pass
    try:
        exec_query("ALTER TABLE ventes ADD COLUMN montant_credit REAL DEFAULT 0.0")
    except: pass

if 'db_structure_ok' not in st.session_state:
    init_db_structure()
    st.session_state['db_structure_ok'] = True
    # st.success("Configuration de la base de données vérifiée.")


# --- FONCTIONS DU PANIER (CORRIGÉES) ---

def add_to_cart_callback(pid, nom, prix, stock, qty, cart_key):
    if qty <= 0:
        st.warning("Veuillez entrer une quantité valide.")
        return
    if qty > stock:
        st.error(f"Stock insuffisant. Seulement {stock} disponibles.")
        return
        
    item_total = prix * qty
    
    # Correction: On vérifie si le produit est déjà dans le panier pour éviter les doublons ou conflits de clés
    for item in st.session_state[cart_key]:
        if item['id'] == pid:
            item['quantite'] += qty
            item['total'] += item_total
            st.success(f"➕ Quantité de {nom} mise à jour dans le panier.")
            return

    # Si ce n'est pas un ajout mais un nouvel article
    st.session_state[cart_key].append({
        'id': pid,
        'nom': nom,
        'prix_u': prix,
        'quantite': qty,
        'total': item_total,
        'stock_dispo': stock # Stock original au moment de l'ajout (pour référence)
    })
    
    st.success(f"➕ {qty} x {nom} (Total: {item_total:.2f} €) ajouté au panier.")

def clear_cart_credit():
    st.session_state['cart_credit'] = []
def clear_cart_cash():
    st.session_state['cart_cash'] = []

# --- Fonction principale de gestion de la vente (CORRIGÉE ET SIMPLIFIÉE) ---
def handle_sale(cart_key, is_credit_sale, client_selection_optional=False):
    current_cart = st.session_state[cart_key]
    if not current_cart:
        st.info("Le panier est vide. Veuillez ajouter des articles.")
        return

    df_cart = pd.DataFrame(current_cart)
    # Ceci garantit le total correct de tous les articles dans la liste
    total_panier = df_cart['total'].sum() 

    col1, col2 = st.columns([1, 1])

    with col1:
        st.subheader("Articles dans le Panier")
        st.dataframe(
            df_cart[['nom', 'quantite', 'prix_u', 'total']],
            column_config={"nom": "Produit", "quantite": "Qté", "prix_u": st.column_config.NumberColumn("Prix U.", format="%.2f €"), "total": st.column_config.NumberColumn("Total", format="%.2f €")},
            hide_index=True, use_container_width=True
        )
        # Le total affiché sera désormais la somme garantie
        st.metric("TOTAL DE LA VENTE", value=f"{total_panier:.2f} €")
        
        if is_credit_sale:
            st.button("Vider le panier crédit", on_click=clear_cart_credit, key=f"clear_{cart_key}")
        else:
            st.button("Vider le panier comptant", on_click=clear_cart_cash, key=f"clear_{cart_key}")

    with col2:
        st.subheader("Finalisation de la Transaction")
        
        clients_db = exec_query("SELECT id, nom, solde_du, plafond_credit FROM clients", fetch=True)
        option_client = {c[1]: (c[0], c[2], c[3]) for c in clients_db} 
        client_choices = ["(Optionnel) Choisir un client"] + list(option_client.keys())
        
        if not client_selection_optional:
             client_choices.pop(0)

        with st.form(f"form_finalize_sale_{cart_key}"):
            
            if is_credit_sale:
                st.markdown("⚠️ **Client OBLIGATOIRE** pour la vente à crédit.")
                choix_client = st.selectbox("Client à créditer", list(option_client.keys()), key=f"sel_client_final_{cart_key}")
            else:
                choix_client = st.selectbox("Client (Pour historique - Optionnel)", client_choices, key=f"sel_client_final_{cart_key}")

            
            if st.form_submit_button(f"✅ Valider la Vente ({'CRÉDIT' if is_credit_sale else 'COMPTANT'})"):
                
                client_id = None
                
                if choix_client and choix_client != "(Optionnel) Choisir un client":
                    cid, solde_du, plafond = option_client[choix_client]
                    client_id = cid
                
                # --- LOGIQUE D'ENREGISTREMENT DU CRÉDIT (SIMPLIFIÉE) ---
                if is_credit_sale:
                    if not client_id:
                        st.error("❌ Veuillez sélectionner un client pour une vente à crédit.")
                        st.stop()
                        
                    nouveau_solde = solde_du + total_panier
                    if nouveau_solde > plafond:
                        st.error(f"❌ CRÉDIT REFUSÉ ! Le solde de {nouveau_solde:.2f} € dépasse le plafond de {plafond:.2f} €.")
                        st.stop()
                    
                    # CORRECTION CRITIQUE: Mise à jour du solde du client (doit être déclenchée ici)
                    sql_update_solde = "UPDATE clients SET solde_du = solde_du + %s WHERE id = %s"
                    exec_query(sql_update_solde, (total_panier, client_id))
                    montant_credit_transaction = total_panier
                else:
                    montant_credit_transaction = 0.0
                
                
                # Enregistrement des produits vendus et mise à jour du stock
                is_first_item = True
                for item in current_cart:
                    
                    # Le montant total du crédit (montant_credit_transaction) n'est enregistré que sur le premier article du panier
                    credit_amount_to_record = montant_credit_transaction if is_first_item else 0.0
                    is_first_item = False 
                    
                    sql_vente = "INSERT INTO ventes (produit_id, quantite, client_id, montant_credit) VALUES (%s, %s, %s, %s)"
                    exec_query(sql_vente, (item['id'], item['quantite'], client_id, credit_amount_to_record))
                    
                    sql_stock = "UPDATE produits SET quantite = quantite - %s WHERE id = %s"
                    exec_query(sql_stock, (item['quantite'], item['id']))
                
                st.success(f"🥳 Vente {('à Crédit' if is_credit_sale else 'Comptant')} enregistrée. Total: {total_panier:.2f} €.")
                
                if is_credit_sale:
                    clear_cart_credit()
                else:
                    clear_cart_cash()
                    
                st.rerun() 


# --- NOUVEAU SYSTÈME DE NAVIGATION PAR ONGLETS (RÉ-INCLUS) ---

tab_vendre, tab_clients, tab_remb, tab_historique, tab_stock, tab_ajouter = st.tabs(
    ["Vendre 🛒", "Clients & Crédit 👤", "Remboursement Client 💵", "Historique Ventes 🧾", "Stock 📦", "Ajouter Produit ➕"]
)

# ----------------------------------------------------
#               ONGLET : VENDRE
# ----------------------------------------------------
with tab_vendre:
    st.header("Sélectionner le Type de Transaction")
    
    tab_credit, tab_cash = st.tabs(["Vente à Crédit 💳", "Vente Comptant 💵"])

    # SOUS-ONGLET CRÉDIT
    with tab_credit:
        st.subheader("1. Ajouter des articles au panier Crédit")
        col_add, col_finalize = st.columns([1, 1])

        with col_add:
            produits_db = exec_query("SELECT id, nom, prix, quantite FROM produits WHERE quantite > 0 ORDER BY nom", fetch=True)
            option_produit = {p[1]: (p[0], p[2], p[3]) for p in produits_db} 
            
            with st.form("form_add_to_cart_credit", clear_on_submit=True):
                choix_produit = st.selectbox("Produit", list(option_produit.keys()) if option_produit else [], key="sel_prod_add_credit")
                
                if choix_produit:
                    pid, prix, stock_actuel = option_produit[choix_produit]
                    st.info(f"Prix unitaire: {prix} € | Stock disponible: {stock_actuel}")
                    
                    qty_add = st.number_input("Quantité à ajouter", min_value=1, max_value=stock_actuel, step=1, value=1, key="qty_add_input_credit")
                    
                    if st.form_submit_button("🛒 Ajouter au Panier Crédit"):
                        add_to_cart_callback(pid, choix_produit, prix, stock_actuel, qty_add, 'cart_credit')

        with col_finalize:
            handle_sale('cart_credit', is_credit_sale=True)

    # SOUS-ONGLET COMPTANT
    with tab_cash:
        st.subheader("1. Ajouter des articles au panier Comptant")
        col_add, col_finalize = st.columns([1, 1])
        
        with col_add:
            produits_db = exec_query("SELECT id, nom, prix, quantite FROM produits WHERE quantite > 0 ORDER BY nom", fetch=True)
            option_produit = {p[1]: (p[0], p[2], p[3]) for p in produits_db} 
            
            with st.form("form_add_to_cart_cash", clear_on_submit=True):
                choix_produit = st.selectbox("Produit", list(option_produit.keys()) if option_produit else [], key="sel_prod_add_cash")
                
                if choix_produit:
                    pid, prix, stock_actuel = option_produit[choix_produit]
                    st.info(f"Prix unitaire: {prix} € | Stock disponible: {stock_actuel}")
                    
                    qty_add = st.number_input("Quantité à ajouter", min_value=1, max_value=stock_actuel, step=1, value=1, key="qty_add_input_cash")
                    
                    if st.form_submit_button("🛒 Ajouter au Panier Comptant"):
                        add_to_cart_callback(pid, choix_produit, prix, stock_actuel, qty_add, 'cart_cash')

        with col_finalize:
            handle_sale('cart_cash', is_credit_sale=False, client_selection_optional=True)


# ----------------------------------------------------
#               ONGLET : REMBOURSEMENT CLIENT
# ----------------------------------------------------
with tab_remb:
    st.header("💵 Enregistrement d'un Paiement/Avance Client")

    clients_db = exec_query("SELECT id, nom, solde_du FROM clients WHERE solde_du > 0 ORDER BY nom", fetch=True)
    option_client = {c[1]: (c[0], c[2]) for c in clients_db} 
    
    if not clients_db:
        st.info("Aucun client n'a de dette en cours (solde dû = 0).")
    else:
        with st.form("form
