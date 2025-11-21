import streamlit as st
import pandas as pd
import psycopg2
import os

# --- Configuration ---
st.set_page_config(page_title="Gestion Stock Pro", layout="centered")
st.title("📦 Gestion de Stock (Sécurisé)")

# --- Connexion Base de Données (PostgreSQL) ---
def get_db_connection():
    try:
        # Récupère l'URL secrète depuis Render
        url = os.environ.get('DATABASE_URL')
        conn = psycopg2.connect(url)
        return conn
    except Exception as e:
        st.error(f"Erreur de connexion : {e}")
        return None

def init_db():
    conn = get_db_connection()
    if conn:
        c = conn.cursor()
        # Création des tables (syntaxe PostgreSQL)
        c.execute('''CREATE TABLE IF NOT EXISTS produits (
            id SERIAL PRIMARY KEY, 
            nom TEXT NOT NULL, 
            prix REAL, 
            quantite INTEGER
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS ventes (
            id SERIAL PRIMARY KEY, 
            produit_id INTEGER, 
            quantite INTEGER, 
            date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')
        conn.commit()
        conn.close()

# Initialiser la DB au démarrage si besoin
if 'db_init' not in st.session_state:
    init_db()
    st.session_state['db_init'] = True

# --- Menu ---
menu = st.sidebar.radio("Menu", ["Vendre", "Stock", "Ajouter Produit"])

if menu == "Ajouter Produit":
    st.header("Nouveau Produit")
    with st.form("ajout_form"):
        nom = st.text_input("Nom")
        prix = st.number_input("Prix", min_value=0.0, step=100.0)
        qty = st.number_input("Quantité", min_value=1, step=1)
        
        if st.form_submit_button("Ajouter"):
            conn = get_db_connection()
            c = conn.cursor()
            c.execute("INSERT INTO produits (nom, prix, quantite) VALUES (%s, %s, %s)", (nom, prix, qty))
            conn.commit()
            conn.close()
            st.success(f"✅ {nom} ajouté !")

elif menu == "Stock":
    st.header("État du Stock")
    conn = get_db_connection()
    # Lire les données avec Pandas
    df = pd.read_sql("SELECT * FROM produits ORDER BY id", conn)
    conn.close()
    st.dataframe(df)

elif menu == "Vendre":
    st.header("Vente")
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT id, nom, quantite FROM produits")
    produits = c.fetchall()
    conn.close()
    
    option_dict = {p[1]: (p[0], p[2]) for p in produits} 
    
    choix = st.selectbox("Produit", list(option_dict.keys()) if option_dict else [])

    if choix:
        pid, stock_actuel = option_dict[choix]
        st.info(f"Stock disponible : {stock_actuel}")
        qty_vendu = st.number_input("Quantité", min_value=1, max_value=stock_actuel, step=1)
        
        if st.button("Valider"):
            conn = get_db_connection()
            c = conn.cursor()
            # Mise à jour du stock
            c.execute("UPDATE produits SET quantite = quantite - %s WHERE id = %s", (qty_vendu, pid))
            # Enregistrement vente
            c.execute("INSERT INTO ventes (produit_id, quantite) VALUES (%s, %s)", (pid, qty_vendu))
            conn.commit()
            conn.close()
            st.success("💰 Vente faite !")
            st.rerun()
