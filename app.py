from flask import Flask, render_template, request, redirect, session
import sqlite3
import bcrypt
app = Flask(__name__)
app.secret_key = "super_secret_key_123"  # 🔐 necessário para sessão

def conectar():
    return sqlite3.connect("sistema_web.db")

def criar_tabelas():
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS usuarios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT,
        email TEXT UNIQUE,
        senha BLOB,
        empresa_id INTEGER
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS produtos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT NOT NULL,
        preco REAL NOT NULL,
        estoque INTEGER DEFAULT 0,
        usuario_id INTEGER,
        empresa_id INTEGER
    )
    """)
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS clientes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT NOT NULL,
        telefone TEXT
    )
    """)
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS empresas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT NOT NULL
    )
    """)
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS vendas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        empresa_id INTEGER NOT NULL,
        usuario_id INTEGER NOT NULL,
        cliente_id INTEGER,
        total REAL NOT NULL,
        data TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS itens_venda (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        venda_id INTEGER NOT NULL,
        produto_id INTEGER NOT NULL,
        quantidade INTEGER NOT NULL,
        preco_unitario REAL NOT NULL
    )
    """)

    conn.commit()
    conn.close()

criar_tabelas()
def criar_admin_padrao():
    conn = conectar()
    cursor = conn.cursor()

    # Verifica se já existe admin
    cursor.execute("SELECT * FROM usuarios WHERE email = ?", ("admin",))
    usuario = cursor.fetchone()

    if not usuario:

        # Criar empresa padrão
        cursor.execute("INSERT INTO empresas (nome) VALUES (?)", ("Empresa Demo",))
        empresa_id = cursor.lastrowid

        senha_hash = bcrypt.hashpw("123".encode("utf-8"), bcrypt.gensalt())

        cursor.execute("""
            INSERT INTO usuarios (nome, email, senha, empresa_id)
            VALUES (?, ?, ?, ?)
        """, ("Administrador", "admin", senha_hash, empresa_id))

        conn.commit()

    conn.close()
    
criar_tabelas()
criar_admin_padrao()
@app.route("/add", methods=["POST"])
def add():

    if "usuario" not in session:
        return redirect("/login")

    nome = request.form["nome"]
    preco = float(request.form["preco"])
    estoque = int(request.form["estoque"])

    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
    INSERT INTO produtos (nome, preco, estoque, empresa_id)
    VALUES (?, ?, ?, ?)
    """, (nome, preco, estoque, session["empresa_id"]))

    conn.commit()
    conn.close()

    return redirect("/dashboard")
    
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":

        email = request.form["email"]
        senha_digitada = request.form["senha"].encode("utf-8")

        conn = conectar()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM usuarios WHERE email=?", (email,))
        usuario = cursor.fetchone()
        conn.close()

        if usuario:
            senha_hash = usuario[3]

            # 🔥 TRATAMENTO CORRETO
            if isinstance(senha_hash, memoryview):
                senha_hash = senha_hash.tobytes()

            if bcrypt.checkpw(senha_digitada, senha_hash):
                session["usuario"] = usuario[1]
                session["usuario_id"] = usuario[0]
                session["empresa_id"] = usuario[4]
                return redirect("/dashboard")

        return "Login inválido"

    return render_template("login.html")
    
    
@app.route("/add_cliente", methods=["POST"])
def add_cliente():

    if "usuario" not in session:
        return redirect("/login")

    nome = request.form["nome"]
    telefone = request.form["telefone"]

    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO clientes (nome, telefone)
        VALUES (?, ?)
    """, (nome, telefone))

    conn.commit()
    conn.close()

    return redirect("/dashboard")

@app.route("/dashboard")
def dashboard():

    if "usuario" not in session:
        return redirect("/login")

    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT * FROM produtos
    WHERE empresa_id = ?
    """, (session["empresa_id"],))
    
    produtos = cursor.fetchall()

    cursor.execute("SELECT * FROM vendas ORDER BY data DESC")
    vendas = cursor.fetchall()

    cursor.execute("SELECT SUM(total) FROM vendas")
    total_geral = cursor.fetchone()[0]
    if total_geral is None:
        total_geral = 0

    # 🔥 AGRUPAR VENDAS POR DIA
    cursor.execute("""
        SELECT DATE(data), SUM(total)
        FROM vendas
        GROUP BY DATE(data)
        ORDER BY DATE(data)
    """)
    dados_grafico = cursor.fetchall()

    datas = [linha[0] for linha in dados_grafico]
    valores = [linha[1] for linha in dados_grafico]

    cursor.execute("SELECT * FROM clientes")
    clientes = cursor.fetchall()

    conn.close()

    return render_template(
        "dashboard.html",
        produtos=produtos,
        vendas=vendas,
        total_geral=total_geral,
        clientes=clientes,
        datas=datas,
        valores=valores
    )
   
@app.route("/cliente/<int:cliente_id>")
def ver_cliente(cliente_id):

    if "usuario" not in session:
        return redirect("/login")

    conn = conectar()
    cursor = conn.cursor()

    # Buscar dados do cliente
    cursor.execute("SELECT * FROM clientes WHERE id = ?", (cliente_id,))
    cliente = cursor.fetchone()

    # Buscar vendas do cliente
    cursor.execute("""
        SELECT id, total, data
        FROM vendas
        WHERE cliente_id = ?
        ORDER BY data DESC
    """, (cliente_id,))
    vendas = cursor.fetchall()

    # Total gasto
    cursor.execute("""
        SELECT SUM(total)
        FROM vendas
        WHERE cliente_id = ?
    """, (cliente_id,))
    total_gasto = cursor.fetchone()[0]

    if total_gasto is None:
        total_gasto = 0

    conn.close()

    return render_template(
        "cliente.html",
        cliente=cliente,
        vendas=vendas,
        total_gasto=total_gasto
    )
    
@app.route("/venda/nova", methods=["POST"])
def nova_venda():
    
    cliente_id = request.form.get("cliente_id")

    if cliente_id == "":
        cliente_id = None

    if "usuario" not in session:
        return redirect("/login")

    conn = conectar()
    cursor = conn.cursor()

    produtos_ids = request.form.getlist("produto_id")

    if not produtos_ids:
        conn.close()
        return redirect("/dashboard")

    total_venda = 0

    # Criar venda
    cursor.execute("""
        INSERT INTO vendas (empresa_id, usuario_id, total)
        VALUES (?, ?, 0)
    """, (session["empresa_id"], session["usuario_id"]))

    venda_id = cursor.lastrowid

    # LOOP para cada produto marcado
    for produto_id in produtos_ids:

        produto_id = int(produto_id)
        quantidade = int(request.form.get(f"quantidade_{produto_id}", 1))

        cursor.execute("""
            SELECT nome, preco, estoque
            FROM produtos
            WHERE id = ?
        """, (produto_id,))

        produto = cursor.fetchone()

        if not produto:
            continue

        nome, preco, estoque = produto

        if estoque < quantidade:
            conn.close()
            return f"Estoque insuficiente para {nome}"

        novo_estoque = estoque - quantidade

        cursor.execute("""
            UPDATE produtos
            SET estoque = ?
            WHERE id = ?
        """, (novo_estoque, produto_id))

        subtotal = preco * quantidade
        total_venda += subtotal

        cursor.execute("""
            INSERT INTO itens_venda
            (venda_id, produto_id, quantidade, preco_unitario)
            VALUES (?, ?, ?, ?)
        """, (venda_id, produto_id, quantidade, preco))

    # Atualizar total da venda
    cursor.execute("""
        UPDATE vendas
        SET total = ?
        WHERE id = ?
    """, (total_venda, venda_id))

    conn.commit()
    conn.close()

    return redirect("/dashboard")
    
@app.route("/cancelar_venda/<int:venda_id>")
def cancelar_venda(venda_id):

    if "usuario" not in session:
        return redirect("/login")

    conn = conectar()
    cursor = conn.cursor()

    # Buscar itens da venda
    cursor.execute("""
        SELECT produto_id, quantidade
        FROM itens_venda
        WHERE venda_id = ?
    """, (venda_id,))

    itens = cursor.fetchall()

    # Devolver estoque
    for produto_id, quantidade in itens:

        cursor.execute("""
            SELECT estoque FROM produtos
            WHERE id = ?
        """, (produto_id,))

        estoque_atual = cursor.fetchone()[0]
        novo_estoque = estoque_atual + quantidade

        cursor.execute("""
            UPDATE produtos
            SET estoque = ?
            WHERE id = ?
        """, (novo_estoque, produto_id))

    # Apagar itens da venda
    cursor.execute("""
        DELETE FROM itens_venda
        WHERE venda_id = ?
    """, (venda_id,))

    # Apagar venda
    cursor.execute("""
        DELETE FROM vendas
        WHERE id = ?
    """, (venda_id,))

    conn.commit()
    conn.close()

    return redirect("/dashboard")
    
@app.route("/registro", methods=["GET", "POST"])
def registro():
    if request.method == "POST":

        nome_empresa = request.form["empresa"]
        nome_usuario = request.form["nome"]
        email = request.form["email"]
        senha = request.form["senha"].encode("utf-8")

        conn = conectar()
        cursor = conn.cursor()

        # Verifica se email já existe
        cursor.execute("SELECT * FROM usuarios WHERE email = ?", (email,))
        if cursor.fetchone():
            conn.close()
            return "Email já cadastrado"

        # Criar empresa
        cursor.execute("""
            INSERT INTO empresas (nome)
            VALUES (?)
        """, (nome_empresa,))
        empresa_id = cursor.lastrowid

        # Criar usuário admin
        senha_hash = bcrypt.hashpw(senha, bcrypt.gensalt())

        cursor.execute("""
            INSERT INTO usuarios (nome, email, senha, empresa_id)
            VALUES (?, ?, ?, ?)
        """, (nome_usuario, email, senha_hash, empresa_id))

        usuario_id = cursor.lastrowid

        conn.commit()
        conn.close()

        # Logar automaticamente
        session["usuario"] = nome_usuario
        session["usuario_id"] = usuario_id
        session["empresa_id"] = empresa_id

        return redirect("/dashboard")

    return render_template("registro.html")
  

@app.route("/logout")
def logout():
    session.pop("usuario", None)
    return redirect("/login")
    
from flask import redirect, url_for

@app.route("/")
def home():
    return redirect("/login")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)