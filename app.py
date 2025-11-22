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

# --- FONCTIONS DE BASE DE DONNÉES ---

def get_db_connection():
    try:
        url = os.environ.get('DATABASE_URL')
        conn = psycopg2.connect(url)
        return conn
    except Exception as e:
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
        return [] if fetch else None

def init_db_structure():
    """Crée les tables et colonnes si elles n'existent pas."""
    exec_query("""CREATE TABLE IF NOT EXISTS produits (id SERIAL PRIMARY KEY, nom TEXT NOT NULL, prix REAL, quantite INTEGER)""")
    exec_query("""CREATE TABLE IF NOT EXISTS ventes (id SERIAL PRIMARY KEY, produit_id INTEGER REFERENCES produits(id), quantite INTEGER, date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
    exec_query("""CREATE TABLE IF NOT EXISTS clients (id SERIAL PRIMARY KEY, nom TEXT NOT NULL, adresse TEXT, plafond_credit REAL DEFAULT 0.0, solde_du REAL DEFAULT 0.0)""")
    exec_query("""CREATE TABLE IF NOT EXISTS paiements (id SERIAL PRIMARY KEY, client_id INTEGER REFERENCES clients(id) NOT NULL, montant REAL NOT NULL, date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")

    exec_query("ALTER TABLE ventes ADD COLUMN client_id INTEGER REFERENCES clients(id)")
    exec_query("ALTER TABLE ventes ADD COLUMN montant_credit REAL DEFAULT 0.0")

if 'db_structure_ok' not in st.session_state:
    init_db_structure()
    st.session_state['db_structure_ok'] = True
    st.success("Configuration de la base de données terminée!")


# --- FONCTIONS DU PANIER ---

def add_to_cart_callback(pid, nom, prix, stock, qty, cart_key):
    if qty <= 0:
        st.warning("Veuillez entrer une quantité valide.")
        return
    if qty > stock:
        st.error(f"Stock insuffisant. Seulement {stock} disponibles.")
        return
        
    item_total = prix * qty
    
    st.session_state[cart_key].append({
        'id': pid,
        'nom': nom,
        'prix_u': prix,
        'quantite': qty,
        'total': item_total,
        'stock_dispo': stock
    })
    
    st.success(f"➕ {qty} x {nom} (Total: {item_total:.2f} €) ajouté au panier.")

def clear_cart_credit():
    st.session_state['cart_credit'] = []
def clear_cart_cash():
    st.session_state['cart_cash'] = []

# --- Fonction principale de gestion de la vente ---
def handle_sale(cart_key, is_credit_sale, client_selection_optional=False):
    current_cart = st.session_state[cart_key]
    if not current_cart:
        st.info("Le panier est vide. Veuillez ajouter des articles.")
        return

    df_cart = pd.DataFrame(current_cart)
    total_panier = df_cart['total'].sum()

    col1, col2 = st.columns([1, 1])

    with col1:
        st.subheader("Articles dans le Panier")
        st.dataframe(
            df_cart[['nom', 'quantite', 'prix_u', 'total']],
            column_config={"nom": "Produit", "quantite": "Qté", "prix_u": st.column_config.NumberColumn("Prix U.", format="%.2f €"), "total": st.column_config.NumberColumn("Total", format="%.2f €")},
            hide_index=True, use_container_width=True
        )
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
                montant_credit = 0.0
                
                if choix_client and choix_client != "(Optionnel) Choisir un client":
                    cid, solde_du, plafond = option_client[choix_client]
                    client_id = cid
                
                if is_credit_sale:
                    if not client_id:
                        st.error("❌ Veuillez sélectionner un client pour une vente à crédit.")
                        st.stop()
                        
                    nouveau_solde = solde_du + total_panier
                    if nouveau_solde > plafond:
                        st.error(f"❌ CRÉDIT REFUSÉ ! Le solde de {nouveau_solde:.2f} € dépasse le plafond de {plafond:.2f} €.")
                        st.stop()
                    
                    montant_credit = total_panier
                    
                    sql_update_solde = "UPDATE clients SET solde_du = solde_du + %s WHERE id = %s"
                    exec_query(sql_update_solde, (total_panier, client_id))
                
                for item in current_cart:
                    is_credit_transaction = montant_credit if item == current_cart[0] else 0.0
                    
                    sql_vente = "INSERT INTO ventes (produit_id, quantite, client_id, montant_credit) VALUES (%s, %s, %s, %s)"
                    exec_query(sql_vente, (item['id'], item['quantite'], client_id, is_credit_transaction))
                    
                    sql_stock = "UPDATE produits SET quantite = quantite - %s WHERE id = %s"
                    exec_query(sql_stock, (item['quantite'], item['id']))
                
                st.success(f"🥳 Vente {('à Crédit' if is_credit_sale else 'Comptant')} enregistrée. Total: {total_panier:.2f} €.")
                
                if is_credit_sale:
                    clear_cart_credit()
                else:
                    clear_cart_cash()
                    
                st.rerun() 


# --- NOUVEAU SYSTÈME DE NAVIGATION PAR ONGLETS ---

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
        with st.form("form_remboursement"):
            choix_client_remb = st.selectbox("Sélectionner le Client qui paie", list(option_client.keys()))
            
            if choix_client_remb:
                cid, solde_actuel = option_client[choix_client_remb]
                st.warning(f"Dette actuelle de {choix_client_remb}: {solde_actuel:.2f} €")
                
                montant_paye = st.number_input(
                    "Montant payé (Avance)", 
                    min_value=0.0, 
                    max_value=solde_actuel, 
                    step=100.0, 
                    key="montant_paye_input"
                )
                
                if st.form_submit_button("Enregistrer le Paiement"):
                    
                    sql_update_solde = "UPDATE clients SET solde_du = solde_du - %s WHERE id = %s"
                    exec_query(sql_update_solde, (montant_paye, cid))
                    
                    sql_paiement = "INSERT INTO paiements (client_id, montant) VALUES (%s, %s)"
                    exec_query(sql_paiement, (cid, montant_paye))
                    
                    nouveau_solde = solde_actuel - montant_paye
                    st.success(f"✅ Paiement de {montant_paye:.2f} € enregistré pour {choix_client_remb}. Nouveau solde dû: {nouveau_solde:.2f} €.")
                    st.rerun()

# ----------------------------------------------------
#               ONGLET : CLIENTS & CRÉDIT
# ----------------------------------------------------
with tab_clients:
    st.header("Gestion des Clients, Plafonds et Historique")

    with st.expander("➕ Ajouter un nouveau client"):
        with st.form("ajout_client_form"):
            nom = st.text_input("Nom du Client")
            adresse = st.text_input("Adresse")
            plafond_credit = st.number_input("Plafond de Crédit Max Autorisé", min_value=0.0, step=500.0, value=0.0)
            
            if st.form_submit_button("Créer le Client"):
                sql = "INSERT INTO clients (nom, adresse, plafond_credit) VALUES (%s, %s, %s)"
                exec_query(sql, (nom, adresse, plafond_credit))
                st.success(f"👤 Client '{nom}' créé avec un plafond de {plafond_credit} €")

    st.subheader("Liste des Clients")
    sql = "SELECT id, nom, adresse, plafond_credit, solde_du FROM clients ORDER BY solde_du DESC"
    df_clients = pd.read_sql(sql, get_db_connection())

    def color_du(val):
        color = 'red' if val > 0 else 'black'
        return f'color: {color}'

    st.dataframe(
        df_clients.style.applymap(color_du, subset=['solde_du']),
        column_config={
            "plafond_credit": st.column_config.NumberColumn("Plafond (€)", format="%.2f"),
            "solde_du": st.column_config.NumberColumn("Solde Dû (€)", format="%.2f")
        },
        use_container_width=True
    )

    st.markdown("---")
    st.subheader("Historique Détaillé du Client (Ventes et Paiements)")
    
    client_list = df_clients['nom'].tolist()
    client_ids = {row['nom']: row['id'] for index, row in df_clients.iterrows()}
    
    if client_list:
        choix_client_hist = st.selectbox("Choisir le client pour l'historique", client_list)
        selected_client_id = client_ids[choix_client_hist]
        
        # 1. Historique des ventes (Produits pris)
        st.markdown("##### 🧾 Produits pris (Comptant et Crédit)")
        sql_ventes = """
        SELECT 
            p.nom AS "Produit",
            v.quantite AS "Qté",
            v.montant_credit AS "Crédit total",
            v.date AS "Date Vente"
        FROM ventes v
        JOIN produits p ON v.produit_id = p.id
        WHERE v.client_id = %s
        ORDER BY v.date DESC
        """
        df_ventes = pd.read_sql(sql_ventes, get_db_connection(), params=(selected_client_id,))
        
        if not df_ventes.empty:
            
            df_ventes['Mode de Paiement'] = df_ventes['Crédit total'].apply(lambda x: "CRÉDIT" if x > 0 else "COMPTANT")
            
            df_ventes['Montant Crédit (€)'] = df_ventes.apply(
                lambda row: row['Crédit total'] if row['Mode de Paiement'] == 'CRÉDIT' else 0.0, axis=1
            )
            
            st.dataframe(df_ventes[['Date Vente', 'Produit', 'Qté', 'Montant Crédit (€)', 'Mode de Paiement']], use_container_width=True)
        else:
            st.info(f"{choix_client_hist} n'a pas de ventes enregistrées (ni comptant, ni crédit).")

        # 2. Historique des paiements (Avances)
        st.markdown("##### 💸 Historique des Paiements (Avances)")
        sql_paiements = """
        SELECT 
            montant AS "Montant Payé (€)",
            date AS "Date Paiement"
        FROM paiements
        WHERE client_id = %s
        ORDER BY date DESC
        """
        df_paiements = pd.read_sql(sql_paiements, get_db_connection(), params=(selected_client_id,))
        
        if not df_paiements.empty:
            st.dataframe(df_paiements, use_container_width=True)
        else:
            st.info(f"{choix_client_hist} n'a pas d'avances enregistrées.")
    else:
        st.info("Veuillez ajouter un client.")


# ----------------------------------------------------
#               ONGLET : HISTORIQUE VENTES
# ----------------------------------------------------
with tab_historique:
    st.header("Historique de Toutes les Transactions")
    
    filtre_mode = st.radio(
        "Filtrer par Mode de Paiement",
        ("Toutes les ventes", "Ventes à Crédit 💳", "Ventes Comptant 💵"),
        horizontal=True
    )
    
    where_clause = ""
    if filtre_mode == "Ventes à Crédit 💳":
        where_clause = "v.montant_credit > 0"
    elif filtre_mode == "Ventes Comptant 💵":
        where_clause = "v.client_id IS NOT NULL AND v.montant_credit = 0"
    
    where_sql = f"WHERE {where_clause}" if where_clause else ""
    
    sql = f"""
    SELECT 
        v.id AS "ID Vente",
        p.nom AS "Produit",
        v.quantite AS "Qté",
        c.nom AS "Client",
        v.montant_credit AS "Montant Crédit (€)",
        v.date AS "Date",
        CASE WHEN v.montant_credit > 0 THEN 'CRÉDIT' WHEN v.client_id IS NOT NULL THEN 'COMPTANT' ELSE 'N/A' END AS "Mode de Paiement"
    FROM ventes v
    JOIN produits p ON v.produit_id = p.id
    LEFT JOIN clients c ON v.client_id = c.id
    {where_sql}
    ORDER BY v.date DESC
    LIMIT 100
    """
    df_history = pd.read_sql(sql, get_db_connection())
    st.dataframe(df_history, use_container_width=True)


# ----------------------------------------------------
#               ONGLET : STOCK
# ----------------------------------------------------
with tab_stock:
    st.header("État du Stock Actuel")
    sql = "SELECT id, nom, prix, quantite FROM produits ORDER BY id"
    df = pd.read_sql(sql, get_db_connection())
    st.dataframe(df, use_container_width=True)

# ----------------------------------------------------
#               ONGLET : AJOUTER PRODUIT
# ----------------------------------------------------
with tab_ajouter:
    st.header("Nouveau Produit")
    with st.form("ajout_produit_form_simple"):
        nom = st.text_input("Nom du produit")
        prix = st.number_input("Prix de vente", min_value=0.0, step=100.0)
        qty = st.number_input("Quantité initiale", min_value=1, step=1)
        
        if st.form_submit_button("Ajouter le Produit"):
            sql = "INSERT INTO produits (nom, prix, quantite) VALUES (%s, %s, %s)"
            exec_query(sql, (nom, prix, qty))
            st.success(f"✅ Produit '{nom}' ajouté !")
