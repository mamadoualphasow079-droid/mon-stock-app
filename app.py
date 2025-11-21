import streamlit as st
import sqlite3
import pandas as pd

# --- Configuration de la page ---
st.set_page_config(page_title="Gestion de Stock", layout="centered")
st.title("📦 Mon Logiciel de Stock")

# --- Gestion Base de Données ---
def init_db():
    conn = sqlite3.connect('stock.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS produits
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, nom TEXT, prix REAL, quantite INTEGER)''')
    c.execute('''CREATE TABLE IF NOT EXISTS ventes
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, produit_id INTEGER, quantite INTEGER, date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    conn.commit()
    return conn

conn = init_db()

# --- Menu de Navigation ---
menu = st.sidebar.radio("Menu", ["Vendre", "Stock", "Ajouter Produit"])

if menu == "Ajouter Produit":
    st.header("Nouveau Produit")
    with st.form("ajout_form"):
        nom = st.text_input("Nom du produit")
        prix = st.number_input("Prix", min_value=0.0, step=0.5)
        qty = st.number_input("Quantité", min_value=1, step=1)
        submitted = st.form_submit_button("Ajouter")
        
        if submitted:
            c = conn.cursor()
            c.execute("INSERT INTO produits (nom, prix, quantite) VALUES (?, ?, ?)", (nom, prix, qty))
            conn.commit()
            st.success(f"✅ {nom} ajouté !")

elif menu == "Stock":
    st.header("État du Stock")
    # Afficher sous forme de joli tableau
    df = pd.read_sql_query("SELECT * FROM produits", conn)
    st.dataframe(df)

elif menu == "Vendre":
    st.header("Enregistrer une Vente")
    # Récupérer la liste des produits pour le menu déroulant
    c = conn.cursor()
    c.execute("SELECT id, nom, quantite FROM produits")
    produits = c.fetchall()
    
    option_dict = {p[1]: (p[0], p[2]) for p in produits} # Nom -> (ID, Stock)
    choix = st.selectbox("Choisir un produit", list(option_dict.keys()) if option_dict else [])

    if choix:
        pid, stock_actuel = option_dict[choix]
        st.info(f"En stock : {stock_actuel}")
        
        qty_vendu = st.number_input("Quantité vendue", min_value=1, max_value=stock_actuel, step=1)
        
        if st.button("Valider la Vente"):
            nouveau_stock = stock_actuel - qty_vendu
            c.execute("UPDATE produits SET quantite = ? WHERE id = ?", (nouveau_stock, pid))
            c.execute("INSERT INTO ventes (produit_id, quantite) VALUES (?, ?)", (pid, qty_vendu))
            conn.commit()
            st.success("💰 Vente enregistrée !")
            st.rerun() # Rafraichir la page
