import os
import io
import asyncio
import discord
import sqlite3
import random
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv
from datetime import datetime, timezone, timedelta
import re
import html
from threading import Lock
from dotenv import load_dotenv

# --- Flask Fake Server ---
from flask import Flask
from threading import Thread

app = Flask('')

@app.route('/')
def home():
    return "Bot rodando!"

def run():
    app.run(host='0.0.0.0', port=5000)

def keep_alive():
    t = Thread(target=run)
    t.start()

keep_alive()  # inicia o servidor Flask

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

bot.run(TOKEN)
# Configuração do banco de dados
criando_ticket = set()
def init_database():
    """Inicializa o banco de dados com as tabelas necessárias"""
    try:
        conn = sqlite3.connect('tickets.db')
        cursor = conn.cursor()
        print("[DATABASE] Conectado ao banco de dados com sucesso!")
        
        # Tabela de tickets
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tickets (
                ticket_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                staff_id TEXT,
                finalizador_id TEXT,
                categoria TEXT,
                data_abertura TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                data_fechamento TIMESTAMP,
                status TEXT DEFAULT 'aberto',
                tempo_resposta INTEGER
            )
        ''')
        
        try:
            cursor.execute('ALTER TABLE tickets ADD COLUMN finalizador_id TEXT')
        except sqlite3.OperationalError:
            pass
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS interacoes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_id TEXT,
                user_id TEXT,
                staff_id TEXT,
                tipo TEXT,
                data TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (ticket_id) REFERENCES tickets (ticket_id)
            )
        ''')

        try:
            cursor.execute('ALTER TABLE interacoes ADD COLUMN staff_id TEXT')
        except:
            pass 
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS avaliacoes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_id TEXT,
                user_id TEXT,
                staff_id TEXT,
                nota INTEGER,
                comentario TEXT,
                data TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (ticket_id) REFERENCES tickets (ticket_id)
            )
        ''')
        
        conn.commit()
        print("[DATABASE] Tabelas criadas/verificadas com sucesso!")
    except sqlite3.Error as e:
        print(f"[DATABASE] Erro ao inicializar o banco de dados: {e}")
    except Exception as e:
        print(f"[DATABASE] Erro inesperado: {e}")
    finally:
        if conn:
            conn.close()

def registrar_ticket(ticket_id, user_id, categoria):
    """Registra um novo ticket no banco de dados"""
    conn = sqlite3.connect('tickets.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO tickets (ticket_id, user_id, categoria)
        VALUES (?, ?, ?)
    ''', (ticket_id, str(user_id), categoria))
    
    conn.commit()
    conn.close()

def fechar_ticket(ticket_id, staff_id, finalizador_id=None):
    """Marca um ticket como fechado no banco de dados"""
    conn = sqlite3.connect('tickets.db')
    cursor = conn.cursor()
    
    if finalizador_id and finalizador_id != staff_id:
        cursor.execute('''
            UPDATE tickets 
            SET status = 'fechado',
                staff_id = ?,
                finalizador_id = ?,
                data_fechamento = CURRENT_TIMESTAMP
            WHERE ticket_id = ?
        ''', (str(staff_id), str(finalizador_id), ticket_id))
    else:
        cursor.execute('''
            UPDATE tickets 
            SET status = 'fechado',
                staff_id = ?,
                data_fechamento = CURRENT_TIMESTAMP
            WHERE ticket_id = ?
        ''', (str(staff_id), ticket_id))
    
    conn.commit()
    conn.close()

def registrar_interacao(ticket_id, user_id, tipo, staff_id=None):
    """Registra uma interação em um ticket"""
    if user_id == bot.user.id if bot.user else 0:
        print(f"[WARNING] Tentativa de registrar bot (ID: {user_id}) em interação - bloqueado")
        return
    
    conn = sqlite3.connect('tickets.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO interacoes (ticket_id, user_id, staff_id, tipo)
        VALUES (?, ?, ?, ?)
    ''', (ticket_id, str(user_id), str(staff_id) if staff_id else None, tipo))
    
    conn.commit()
    conn.close()

def obter_estatisticas():
    """Retorna estatísticas gerais dos tickets"""
    conn = sqlite3.connect('tickets.db')
    cursor = conn.cursor()
    
    # Total de tickets
    cursor.execute('SELECT COUNT(*) FROM tickets')
    total_tickets = cursor.fetchone()[0]
    
    # Tickets abertos
    cursor.execute('SELECT COUNT(*) FROM tickets WHERE status = "aberto"')
    tickets_abertos = cursor.fetchone()[0]
    
    # Tickets por categoria
    cursor.execute('''
        SELECT categoria, COUNT(*) 
        FROM tickets 
        GROUP BY categoria
    ''')
    categorias = cursor.fetchall()
    
    cursor.execute('''
        SELECT AVG((strftime('%s', data_fechamento) - strftime('%s', data_abertura))/60)
        FROM tickets 
        WHERE status = 'fechado'
    ''')
    tempo_medio = cursor.fetchone()[0]
    
    conn.close()
    
    return {
        'total_tickets': total_tickets,
        'tickets_abertos': tickets_abertos,
        'categorias': dict(categorias),
        'tempo_medio_resolucao': tempo_medio
    }

def obter_ranking_tickets_abertos():
    """Retorna o ranking de usuários que mais abriram tickets"""
    conn = sqlite3.connect('tickets.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT user_id, COUNT(*) as quantidade
        FROM tickets 
        GROUP BY user_id
        ORDER BY quantidade DESC
        LIMIT 15
    ''')
    
    ranking = cursor.fetchall()
    conn.close()
    return ranking

def obter_ranking_tickets_assumidos():
    """Retorna o ranking de staff que mais assumiram tickets"""
    conn = sqlite3.connect('tickets.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT staff_id, COUNT(*) as quantidade
        FROM tickets 
        WHERE staff_id IS NOT NULL
        GROUP BY staff_id
        ORDER BY quantidade DESC
        LIMIT 15
    ''')
    
    ranking = cursor.fetchall()
    conn.close()
    
    ranking_filtrado = []
    for staff_data in ranking:
        staff_id = int(staff_data[0])
        if staff_id != bot.user.id if bot.user else 0:
            ranking_filtrado.append(staff_data)
    
    return ranking_filtrado

async def limpar_dados_bot_do_banco():
    """Remove dados do bot do banco de dados para evitar que apareça no ranking"""
    if not bot.user:
        print("[WARNING] Bot user não está disponível ainda, pulando limpeza")
        return
        
    bot_id = str(bot.user.id)
    print(f"[CLEANUP] Limpando dados do bot (ID: {bot_id}) do banco de dados...")
    
    conn = sqlite3.connect('tickets.db')
    cursor = conn.cursor()
    
    try:
        cursor.execute('UPDATE tickets SET staff_id = NULL WHERE staff_id = ?', (bot_id,))
        tickets_atualizados = cursor.rowcount
        
        cursor.execute('DELETE FROM interacoes WHERE user_id = ? OR staff_id = ?', (bot_id, bot_id))
        interacoes_removidas = cursor.rowcount
        
        conn.commit()
        
        if tickets_atualizados > 0:
            print(f"[CLEANUP] Removido bot de {tickets_atualizados} tickets")
        if interacoes_removidas > 0:
            print(f"[CLEANUP] Removidas {interacoes_removidas} interações do bot")
            
        if tickets_atualizados == 0 and interacoes_removidas == 0:
            print("[CLEANUP] Nenhum dado do bot encontrado no banco (está limpo)")
            
    except Exception as e:
        print(f"[ERROR] Erro ao limpar dados do bot: {e}")
    finally:
        conn.close()

async def limpar_bot_da_memoria():
    """Remove o bot das estruturas de dados em memória"""
    if not bot.user:
        print("[WARNING] Bot user não está disponível ainda, pulando limpeza da memória")
        return
        
    bot_id = bot.user.id
    tickets_limpos = 0
    
    for channel_id, staff_list in list(ticket_assumido_por.items()):
        if bot_id in staff_list:
            staff_list.remove(bot_id)
            tickets_limpos += 1
            print(f"[CLEANUP] Bot removido do ticket {channel_id} na memória")
    
    if tickets_limpos == 0:
        print("[CLEANUP] Bot não encontrado em nenhum ticket na memória (está limpo)")
    else:
        print(f"[CLEANUP] Bot removido de {tickets_limpos} tickets na memória")

def registrar_staff_assumindo_ticket(ticket_id, staff_id):
    """Registra que um staff assumiu um ticket"""
    if staff_id == bot.user.id if bot.user else 0:
        print(f"[WARNING] Tentativa de registrar bot (ID: {staff_id}) como staff assumindo ticket - bloqueado")
        return False
    
    conn = sqlite3.connect('tickets.db')
    conn.isolation_level = "EXCLUSIVE"
    cursor = conn.cursor()
    
    try:
        cursor.execute("BEGIN EXCLUSIVE TRANSACTION")

        cursor.execute('''
            SELECT staff_id FROM tickets WHERE ticket_id = ? AND staff_id IS NOT NULL
        ''', (ticket_id,))
        
        existente = cursor.fetchone()
        if existente:
            conn.rollback()
            conn.close()
            return False

        cursor.execute('''
            UPDATE tickets 
            SET staff_id = ?
            WHERE ticket_id = ?
        ''', (str(staff_id), ticket_id))
        
        conn.commit()
        return True
    except sqlite3.Error as e:
        conn.rollback()
        print(f"[DATABASE] Erro ao registrar staff assumindo ticket: {e}")
        return False
    finally:
        conn.close()

init_database()

def get_formatted_time():
    """Retorna o horário formatado"""
    now = datetime.now()
    return now.strftime('%d/%m/%Y às %H:%M')

async def assumir_ticket_seguro(ticket_id, staff_id):
    """
    Função auxiliar para assumir tickets com segurança contra condições de corrida
    Retorna True se o ticket foi assumido com sucesso, False caso contrário
    """
    with assumir_lock:
        # Verifica se o ticket já está assumido na memória
        if ticket_id in ticket_assumido_por and ticket_assumido_por[ticket_id]:
            return False
            
        # Tenta registrar no banco de dados
        sucesso = registrar_staff_assumindo_ticket(ticket_id, staff_id)
        if not sucesso:
            return False
            
        # Se deu certo no banco de dados
        ticket_assumido_por.setdefault(ticket_id, []).append(staff_id)
        
        # Registrar interação do staff assumindo o ticket
        registrar_interacao(ticket_id, staff_id, "assumir", staff_id)
        
        return True

load_dotenv()
TOKEN = os.getenv("TOKEN")

if not TOKEN:
    print("Token do bot não encontrado! Configure a variável TOKEN no arquivo .env")
    exit()

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# IDs e Configurações
STAFF_ROLE_ID = 1253467045467652178
YOUR_GUILD_ID = 1062770004380106752
AVALIACOES_CHANNEL_ID = 1387616027558543361

# Super Admins
ALLOWED_USER_IDS = [1058559223765676174, 881757749241872384, 618446962475270147, 241233786136821761, 1073738770559537192, 848672913934385224, 1061802170263019520]  # Substitua pelos IDs reais

def has_staff_permissions(user, guild):
    """Verifica se o usuário tem permissões básicas de staff (cargo)"""
    staff_role = guild.get_role(STAFF_ROLE_ID)
    if staff_role and staff_role in user.roles:
        return True
    return False

def has_admin_permissions(user, guild):
    """Verifica se o usuário tem permissões administrativas completas (ALLOWED_USER_IDS)"""
    if user.id in ALLOWED_USER_IDS:
        return True
    return False

def can_use_advanced_features(user, guild):
    """Verifica se pode usar funcionalidades avançadas (só admins)"""
    return has_admin_permissions(user, guild)

# Categorias para tipos de tickets
CATEGORY_IDS = {
    "apelação": 1387562695703662642,
    "Denúncia": 1387562717489004696,
    "suporte": 1387562651139309638,
    "VIPs": 1367219064996495450,
}

# Canais de transcript
TRANSCRIPT_CHANNELS = {
    "apelação": 1404870936846405714, 
    "Denúncia": 1404870797050384466, 
    "suporte": 1404870831112192072,    
    "VIPs": 1404871235665662042    
}

# Canal de transcript canal de logs
TRANSCRIPT_CHANNEL_ID = 1387555443290669218
LOG_CHANNEL_ID = 1387555443290669218

RESPOSTAS_PREDEFINIDAS = {
    "vip": """**<:3Carto:1396678216734867637> Chave PIX: 10.368.717/0001-44**

**<:3Bolsa:1396678197927481405> Planos disponíveis:**

> <:3Calendario:1396678204680310957> 1 mês – R$ 6,99
> <:3Calendario:1396678204680310957> 2 meses – R$ 10,99
> <:3Calendario:1396678204680310957> 4 meses – R$ 16,99

**<:4Mensagem:1396875577952047114> Após o pagamento, envie o comprovante diretamente aqui no chat.**""",
    
    "form": """**<:0Anncios:1396675340532711424> Por favor, avalie os Staffs que te atenderam no ticket:
https://forms.gle/JM353PJgJML1ypfC8
ou, se preferir: <:4Discord:1396875572369424454> Canal no Discord https://discord.com/channels/1062770004380106752/1384324863556321502

Sua opinião ajuda a melhorar o atendimento! <:3Positivo:1396875464081018920>**""",
    
    "unban": """**<:3Estrela:1396678251086348338> MULTA HDTZ <:3Estrela:1396678251086348338>**

> Foi banido por nível ou por toxicidade? Agora tem multa!
> Quanto mais repetir, mais caro fica!

**<:3Banimento:1396678181741662353> Nível:**
1ª vez: R$1,50 | 2ª vez: R$3,00 | 3ª vez ou mais: R$4,50

**<:52Toxico:1396609701562810419> Toxicidade:**
1ª vez: R$3,00 | 2ª vez: R$6,00 | 3ª vez ou mais: R$9,00

**<:52Toxico:1396609701562810419> Toxicidade Grave**
1ª vez: R$5,00 | 2ª vez: R$10,00 | 3ª vez ou mais: R$15,00

> <:3Substituio:1396875469915160776> As multas são resetadas todo dia 1º do mês
> <:3Denncia:1396678232413310987> Ban por racismo ou evasão não tem direito a multa!

**<:3Carto:1396678216734867637> Chave Pix: 10.368.717/0001-44**

**<:4Mensagem:1396875577952047114> Após o pagamento, envie o comprovante diretamente aqui no chat.**""",
    
    "parceria": """**<:3Carto:1396678216734867637> Chave PIX para pagamento: 10.368.717/0001-44**

> <:3Membro:1396885356334415922> 0 a 50 membros: R$ 35
> <:3Membro:1396885356334415922> 51 a 100 membros: R$ 30
> <:3Membro:1396885356334415922> 101 a 200 membros: R$ 25
> <:3Membro:1396885356334415922> 201 a 300 membros: R$ 20

**Assim que fizer o pagamento, envie o comprovante aqui mesmo no ticket e daremos continuidade à parceria. <:0Parcerias:1396675336791396504>**

**Ficamos à disposição para qualquer dúvida!**"""
}

# Prefixos e emojis para os tickets
TICKET_PREFIXES = {
    "apelação": "APL",
    "Denúncia": "REP", 
    "suporte": "SUP",
    "VIPs": "VIP"
}

TICKET_EMOJIS = {
    "apelação": "⚖️",    
    "Denúncia": "🚨",    
    "suporte": "🛠️",     
    "VIPs": "👑"        
}

# Dicionários de controle
ticket_assumido_por = {}
# Lock para operações de assumir ticket
assumir_lock = Lock()
ticket_membros_adicionados = {}
ticket_types = {}  # Armazena o tipo de cada ticket por ID
unban_cooldown = {}  # Armazena o último uso do botão Unban por usuário
respostas_staff = {}  # Armazena as respostas rápidas personalizadas de cada staff
tickets_finalizados = {}  # Armazena tickets que foram finalizados e estão aguardando fechamento automático
tickets_monitoramento = {}  # Armazena dados de monitoramento de tickets para sistema de 5 horas
ticket_creation_cooldown = {}  # user_id: timestamp
TICKET_COOLDOWN_SECONDS = 15  # 15 segundos entre criações de ticket

MAX_TICKETS_PER_USER = 2

def get_ticket_author(channel):
    async def inner():
        async for msg in channel.history(limit=20, oldest_first=True):
            if msg.embeds:
                embed = msg.embeds[0]
                for field in embed.fields:
                    if "Usuário:" in field.value:
                        match = re.search(r"<@!?(?P<id>\d+)>", field.value)
                        if match:
                            return int(match.group("id"))
        return None
    return inner

async def fechar_ticket_automatico(channel_id, guild, delay_seconds=43200):
    """Agenda o fechamento automático de um ticket após o delay especificado"""
    await asyncio.sleep(delay_seconds)
    
    if channel_id not in tickets_finalizados:
        return
    
    channel = guild.get_channel(channel_id)
    if not channel:
        tickets_finalizados.pop(channel_id, None)
        return
    
    try:
        # Obtém informações do ticket
        get_author = get_ticket_author(channel)
        author_id = await get_author()
        
        # Gera o transcript
        ticket_type = ticket_types.get(channel_id, "suporte")
        transcript_channel_id = TRANSCRIPT_CHANNELS.get(ticket_type, TRANSCRIPT_CHANNEL_ID)
        transcript_channel = guild.get_channel(transcript_channel_id)
        
        if transcript_channel:
            file = await gerar_transcript_html(channel)
            
            # Obtém informações de quem finalizou
            finalizacao_info = tickets_finalizados.get(channel_id, {})
            staff_id = finalizacao_info.get("staff_id")
            staff_mention = f"<@{staff_id}>" if staff_id else "Staff desconhecido"
            
            embed = discord.Embed(
                title=f"{TICKET_EMOJIS.get(ticket_type, '🎫')} Ticket Fechado Automaticamente ({ticket_type.capitalize() if ticket_type else 'Desconhecido'})",
                description=f"Este ticket foi **finalizado por {staff_mention}** e fechado automaticamente após 12 horas.",
                color=discord.Color.from_rgb(255, 186, 0),
                timestamp=datetime.now()
            )
            
            modal_data = finalizacao_info.get("modal_data")
            
            if modal_data:
                if "motivo_fechar" in modal_data:
                    embed.add_field(name="Motivo por fechar", value=modal_data["motivo_fechar"], inline=False)
                if "sala" in modal_data and modal_data["sala"]:
                    embed.add_field(name="Sala", value=modal_data["sala"], inline=False)
            else:
                embed.add_field(name="Motivo do fechamento", value="Fechamento automático após finalização", inline=False)
            
            embed.add_field(name="📋 Finalizado por", value=staff_mention, inline=True)
            embed.add_field(name="⏰ Tempo de espera", value="12 horas", inline=True)
            embed.set_footer(text="HDTZ - Sistema de Tickets (Auto)")
            
            await transcript_channel.send(
                f"**🤖 | Transcript do ticket `{channel.name}` fechado automaticamente:**\n**TicketID:** `{author_id}`\n**Finalizado por:** {staff_mention}",
                embed=embed,
                file=file
            )
        
        parar_monitoramento_ticket(channel_id)

        finalizacao_info = tickets_finalizados.get(channel_id, {})
        finalizador_id = finalizacao_info.get("staff_id")
        fechar_ticket(channel_id, guild.me.id, finalizador_id)
        
        ticket_assumido_por.pop(channel_id, None)
        ticket_membros_adicionados.pop(channel_id, None)
        ticket_types.pop(channel_id, None)
        tickets_finalizados.pop(channel_id, None)
        
        await channel.delete()
        
    except Exception as e:
        print(f"Erro ao fechar ticket automaticamente: {e}")
        tickets_finalizados.pop(channel_id, None)

def escape_markdown(text):
    text = text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    return text

def render_discord_emojis(text):
    emoji_pattern = re.compile(r'<(a?):([a-zA-Z0-9_]+):(\d+)>')
    def replacer(match):
        animated, name, eid = match.groups()
        ext = 'gif' if animated else 'png'
        url = f"https://cdn.discordapp.com/emojis/{eid}.{ext}"
        return f'<img src="{url}" alt=":{name}:" style="height:1em;vertical-align:-0.1em;">'
    return emoji_pattern.sub(replacer, text)

def markdown_to_html(text):
    text = escape_markdown(text)
    text = re.sub(r'(\*\*|__)(.*?)\1', r'<b>\2</b>', text)
    text = re.sub(r'(\*|_)(.*?)\1', r'<i>\2</i>', text)
    text = re.sub(r'`([^`]+)`', r'<code>\1</code>', text)
    text = re.sub(r'\|\|(.+?)\|\|', r'<span style="background:#eee;border-radius:3px;padding:0 3px;">\1</span>', text)
    text = re.sub(r'https?://\S+', lambda m: f'<a href="{m.group(0)}" target="_blank">{m.group(0)}</a>', text)
    text = render_discord_emojis(text)
    return text

async def user_ticket_count(guild, user):
    count = 0
    for channel in guild.channels:
        if channel.name.startswith("🎫・") and isinstance(channel, discord.TextChannel):
            get_author = get_ticket_author(channel)
            author_id = await get_author()
            if author_id and author_id == user.id:
                count += 1
    return count


def eh_horario_madrugada():
    """Verifica se o horário atual está entre 00:00 e 07:00 (horário de Brasília)"""
    agora = datetime.now(timezone.utc)
    hora_br = (agora.hour - 3) % 24
    return 0 <= hora_br < 7

def calcular_tempo_ativo_ticket(timestamp_inicial):
    """Calcula o tempo ativo de um ticket, excluindo o período da madrugada (00:00-07:00)"""
    agora = datetime.now(timezone.utc)
    tempo_total = 0
    
    # Converte timestamp inicial para datetime se necessário
    if isinstance(timestamp_inicial, (int, float)):
        inicio = datetime.fromtimestamp(timestamp_inicial, tz=timezone.utc)
    else:
        inicio = timestamp_inicial
    
    data_atual = inicio.date()
    fim_data = agora.date()
    
    while data_atual <= fim_data:
        if data_atual == inicio.date():
            inicio_dia = inicio
        else:
            inicio_dia = datetime.combine(data_atual, datetime.min.time(), timezone.utc)
        
        if data_atual == fim_data:
            fim_dia = agora
        else:
            fim_dia = datetime.combine(data_atual, datetime.max.time(), timezone.utc)
        
        for hora in range(24):
            hora_br = (hora - 3) % 24
            if 7 <= hora_br < 24:
                hora_inicio = datetime.combine(data_atual, datetime.min.time().replace(hour=hora), timezone.utc)
                hora_fim = datetime.combine(data_atual, datetime.min.time().replace(hour=hora, minute=59, second=59), timezone.utc)
                
                # Verifica se há overlap com o período do ticket
                if hora_inicio <= fim_dia and hora_fim >= inicio_dia:
                    inicio_overlap = max(hora_inicio, inicio_dia)
                    fim_overlap = min(hora_fim, fim_dia)
                    tempo_total += (fim_overlap - inicio_overlap).total_seconds()
        
        data_atual += timedelta(days=1)
    
    return tempo_total / 3600

async def obter_top3_staff_rankings():
    """Obtém os top 3 staff que mais assumiram tickets"""
    ranking = obter_ranking_tickets_assumidos()
    return ranking[:3] if ranking else []

async def sortear_staff_para_ticket(guild, channel_id):
    """Sorteia um dos top 3 staff para ser adicionado ao ticket"""
    try:
        top3_staff = await obter_top3_staff_rankings()
        
        if not top3_staff:
            print(f"[MONITORAMENTO] Nenhum staff encontrado no ranking para o ticket {channel_id}")
            return None
        
        staff_sorteado_data = random.choice(top3_staff)
        staff_id = int(staff_sorteado_data[0])
        
        if staff_id == bot.user.id if bot.user else 0:
            print(f"[MONITORAMENTO] Bot foi sorteado, tentando novamente...")
            top3_filtrado = [s for s in top3_staff if int(s[0]) != (bot.user.id if bot.user else 0)]
            if not top3_filtrado:
                print(f"[MONITORAMENTO] Nenhum staff válido encontrado após filtrar o bot")
                return None
            staff_sorteado_data = random.choice(top3_filtrado)
            staff_id = int(staff_sorteado_data[0])
        
        staff_member = guild.get_member(staff_id)
        if not staff_member:
            print(f"[MONITORAMENTO] Staff {staff_id} não encontrado no servidor")
            return None
            
        if staff_member.bot:
            print(f"[MONITORAMENTO] Staff selecionado {staff_member.name} é um bot, pulando...")
            return None
        
        if staff_id in ticket_assumido_por.get(channel_id, []):
            print(f"[MONITORAMENTO] Staff {staff_member.name} já está no ticket {channel_id}")
            return None
        
        return staff_member
        
    except Exception as e:
        print(f"[MONITORAMENTO] Erro ao sortear staff: {e}")
        return None

async def adicionar_staff_automaticamente(guild, channel, staff_member):
    """Adiciona um staff automaticamente ao ticket e atualiza as permissões"""
    try:
        channel_id = channel.id
        
        if staff_member.id == bot.user.id if bot.user else 0:
            print(f"[WARNING] Tentativa de adicionar bot automaticamente ao ticket {channel_id} - bloqueado")
            return False
            
        if staff_member.bot:
            print(f"[WARNING] Tentativa de adicionar bot {staff_member.name} automaticamente ao ticket {channel_id} - bloqueado")
            return False
        
        # Adiciona o staff ao ticket
        await channel.set_permissions(
            staff_member,
            view_channel=True,
            send_messages=True,
            read_messages=True,
            manage_messages=True,
            attach_files=True,
            embed_links=True
        )
        
        # Atualiza o dicionário de controle
        ticket_assumido_por.setdefault(channel_id, []).append(staff_member.id)
        
        # Registra no banco de dados
        registrar_staff_assumindo_ticket(channel_id, staff_member.id)
        
        registrar_interacao(channel_id, staff_member.id, "adicionado_automatico", staff_member.id)
        
        embed = discord.Embed(
            title="<:0Anncios:1396675340532711424> Sistema Automático | Staff Adicionado",
            description=(
                f"**<:3Relogio:1396875467218489344> Este ticket ficou 1 hora sem resposta.**\n\n"
                f"<:3Sorte:1404875103916789891> **Staff sorteado automaticamente:** {staff_member.mention}\n"
                f"<:0Campeonato:1396675343317733406> **Motivo:** Top 3 em tickets assumidos\n\n"
                f"<:0Parcerias:1396675336791396504> **{staff_member.mention}, você foi selecionado para ajudar neste ticket!**"
            ),
            color=discord.Color.from_rgb(0, 255, 127),
            timestamp=datetime.now()
        )
        embed.set_footer(text="HDTZ - Sistema de Monitoramento Automático")
        
        await channel.send(embed=embed)
        
        await atualizar_embed_ticket_com_staff(channel, staff_member)
        
        print(f"[MONITORAMENTO] Staff {staff_member.name} adicionado automaticamente ao ticket {channel_id}")
        return True
        
    except Exception as e:
        print(f"[MONITORAMENTO] Erro ao adicionar staff automaticamente: {e}")
        return False

async def atualizar_embed_ticket_com_staff(channel, staff_member):
    """Atualiza a embed inicial do ticket com o novo staff"""
    try:
        async for msg in channel.history(limit=20, oldest_first=True):
            if msg.embeds and msg.author.bot:
                embed = msg.embeds[0]
                if "Informações do Ticket:" in embed.fields[0].name:
                    for i, field in enumerate(embed.fields):
                        if "Staff responsável:" in field.value:
                            staff_atual = ticket_assumido_por.get(channel.id, [])
                            staff_mentions = ', '.join(f'<@{uid}>' for uid in staff_atual) if staff_atual else "Ticket não assumido."
                            
                            novo_valor = field.value.split("Staff responsável:")[0] + f"Staff responsável:** {staff_mentions}"
                            embed.set_field_at(i, name=field.name, value=novo_valor, inline=field.inline)
                            break
                    
                    await msg.edit(embed=embed)
                    break
    except Exception as e:
        print(f"[MONITORAMENTO] Erro ao atualizar embed: {e}")

async def iniciar_monitoramento_ticket(channel_id, guild):
    """Inicia o monitoramento de um ticket para verificar se fica 1 hora sem resposta"""
    try:
        agora = datetime.now(timezone.utc)
        
        # Adiciona ao dicionário de monitoramento
        tickets_monitoramento[channel_id] = {
            'inicio_monitoramento': agora,
            'ultima_resposta_staff': None,
            'guild': guild,
            'notificado': False
        }
        
        print(f"[MONITORAMENTO] Iniciado monitoramento para ticket {channel_id}")
        
        # Inicia task de monitoramento
        asyncio.create_task(monitorar_ticket_inativo(channel_id))
        
    except Exception as e:
        print(f"[MONITORAMENTO] Erro ao iniciar monitoramento: {e}")

async def monitorar_ticket_inativo(channel_id):
    """Monitora um ticket e adiciona staff se ficar 1 hora sem resposta (excluindo madrugada)"""
    try:
        while channel_id in tickets_monitoramento:
            await asyncio.sleep(300)
            
            if channel_id not in tickets_monitoramento:
                break
            
            dados_monitoramento = tickets_monitoramento[channel_id]
            guild = dados_monitoramento['guild']

            channel = guild.get_channel(channel_id)
            if not channel:
                tickets_monitoramento.pop(channel_id, None)
                break
            
            if dados_monitoramento.get('notificado', False):
                continue
            
            # Verifica se há staff no ticket
            if ticket_assumido_por.get(channel_id):
                continue
            
            inicio = dados_monitoramento['inicio_monitoramento']
            tempo_ativo = calcular_tempo_ativo_ticket(inicio)
            
            if tempo_ativo >= 1.0:
                staff_sorteado = await sortear_staff_para_ticket(guild, channel_id)
                
                if staff_sorteado:
                    sucesso = await adicionar_staff_automaticamente(guild, channel, staff_sorteado)
                    if sucesso:
                        dados_monitoramento['notificado'] = True
                        dados_monitoramento['staff_adicionado'] = staff_sorteado.id
                        dados_monitoramento['tempo_adicao'] = datetime.now(timezone.utc)
                        
                        print(f"[MONITORAMENTO] Staff {staff_sorteado.name} adicionado ao ticket {channel_id} após 1 hora")
                else:
                    print(f"[MONITORAMENTO] Não foi possível sortear staff para o ticket {channel_id}")
                    dados_monitoramento['notificado'] = True
    
    except Exception as e:
        print(f"[MONITORAMENTO] Erro no monitoramento do ticket {channel_id}: {e}")
    finally:
        if channel_id in tickets_monitoramento:
            tickets_monitoramento.pop(channel_id, None)
            print(f"[MONITORAMENTO] Monitoramento finalizado para ticket {channel_id}")

def parar_monitoramento_ticket(channel_id):
    """Para o monitoramento de um ticket"""
    if channel_id in tickets_monitoramento:
        tickets_monitoramento.pop(channel_id, None)
        print(f"[MONITORAMENTO] Monitoramento parado para ticket {channel_id}")


async def gerar_transcript_html(channel: discord.TextChannel) -> discord.File:
    staff_role = channel.guild.get_role(STAFF_ROLE_ID)
    messages = []
    last_author_id = None
    last_date = None
    command_history = []

    async for msg in channel.history(limit=None, oldest_first=True):
        if msg.content.startswith('!') or msg.content.startswith('/'):
            command_history.append({
                'author': msg.author.name,
                'command': msg.content,
                'timestamp': msg.created_at.strftime('%d/%m/%Y %H:%M:%S')
            })

        if msg.author.bot and not msg.embeds:
            continue

        msg_datetime = msg.created_at.astimezone(timezone.utc)
        ts = msg_datetime.strftime('%d/%m/%Y %H:%M')
        msg_date = msg_datetime.date()

        if last_date != msg_date:
            messages.append(
                f'<div style="text-align:center;color:#999;font-size:15px;margin:25px 0 10px 0;"><b>── {msg_date.strftime("%d/%m/%Y")} ──</b></div>'
            )
            last_date = msg_date

        is_staff = has_staff_permissions(msg.author, msg.guild) or has_admin_permissions(msg.author, msg.guild)
        avatar_url = msg.author.display_avatar.url if hasattr(msg.author, "display_avatar") else (msg.author.avatar.url if msg.author.avatar else "")
        avatar_img = f'<img src="{avatar_url}" width="32" height="32" style="border-radius:50%;vertical-align:middle;margin-right:8px;border:1.5px solid #e0e0e0;">' if avatar_url else ""

        roles_html = ""
        if hasattr(msg.author, "roles"):
            roles = [role for role in msg.author.roles if role.name != "@everyone"]
            main_roles = sorted(roles, key=lambda r: r.position, reverse=True)[:2]
            for r in main_roles:
                roles_html += f'<span style="background:{r.color};color:#fff;border-radius:3px;padding:1px 6px;font-size:11px;margin-left:6px;">{html.escape(r.name)}</span>'

        reply_html = ""
        if msg.reference and msg.reference.resolved:
            ref = msg.reference.resolved
            author = getattr(ref, "author", None)
            ref_content = getattr(ref, "content", "")
            if author:
                reply_html = (
                    f'<div style="font-size:12px;color:#888;background:#ededed;border-left:3px solid #aaa;padding:3px 8px 3px 8px;border-radius:4px 6px 6px 4px;margin-bottom:3px;">'
                    f'Resposta a <b>{html.escape(author.display_name)}</b>: {markdown_to_html(html.escape(ref_content[:60]))}'
                    + ("..." if len(ref_content) > 60 else "") +
                    f'</div>'
                )

        content = markdown_to_html(msg.content) if msg.content else ""

        images_html = ""
        files_html = ""
        for a in msg.attachments:
            if a.content_type and "image" in a.content_type:
                images_html += f'<br><a href="{a.url}" target="_blank"><img src="{a.url}" style="max-width:220px;max-height:220px;margin-top:4px;border-radius:4px;box-shadow:0 2px 12px #bbb;"></a>'
            else:
                files_html += f'<br><a href="{a.url}" target="_blank" style="color:#0055aa;font-size:13px;">{html.escape(a.filename)}</a>'

        message_url = f"https://discord.com/channels/{channel.guild.id}/{channel.id}/{msg.id}"

        bg = "#36393f" if is_staff else "#23272a"
        border = "2px solid #7289da" if is_staff else "1px solid #23272a"

        show_header = last_author_id != msg.author.id or reply_html or roles_html
        header_html = ""
        if show_header:
            header_html = (
                f'{avatar_img}'
                f'<span style="color:#888;font-size:13px;">[{ts}]</span> '
                f'<b style="color:#0055aa;font-size:15px;">{html.escape(msg.author.display_name)}</b>'
                f'{roles_html} '
                f'<a href="{message_url}" style="color:#bbb;font-size:11px;margin-left:6px;text-decoration:none;" title="Ver no Discord">🔗</a>'
            )

        messages.append(
            f"""
            <div style="margin-bottom:9px;padding:10px 15px;background:{bg};border-radius:8px;box-shadow:1px 1px 6px #222;border:{border};color:#fff;">
                {(header_html+"<br>") if show_header else ""}
                {reply_html}
                <div style="margin-left:{'40px' if show_header else '0'};margin-top:2px;font-size:15px;">
                {content if content else ""}
                {images_html}{files_html}
                </div>
            </div>
            """
        )
        last_author_id = msg.author.id

    command_section = ""
    if command_history:
        command_section = """
        <div style="margin: 20px 0;padding: 15px;background: #2f3136;border-radius: 8px;">
            <h3 style="color: #fff;margin-bottom: 10px;">📋 Histórico de Comandos</h3>
            <table style="width: 100%;border-collapse: collapse;color: #fff;">
                <tr style="border-bottom: 1px solid #40444b;">
                    <th style="padding: 8px;text-align: left;">Horário</th>
                    <th style="padding: 8px;text-align: left;">Usuário</th>
                    <th style="padding: 8px;text-align: left;">Comando</th>
                </tr>
        """
        for cmd in command_history:
            command_section += f"""
                <tr style="border-bottom: 1px solid #40444b;">
                    <td style="padding: 8px;">{cmd['timestamp']}</td>
                    <td style="padding: 8px;">{html.escape(cmd['author'])}</td>
                    <td style="padding: 8px;"><code style="background: #202225;padding: 2px 6px;border-radius: 3px;">{html.escape(cmd['command'])}</code></td>
                </tr>
            """
        command_section += """
            </table>
        </div>
        """

    html_content = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <title>Transcript - {html.escape(channel.name)}</title>
    <meta name="viewport" content="width=device-width,initial-scale=1">
    <style>
        body {{ font-family:sans-serif;background:#2c2f33;margin:0;padding:0; color:#ddd; }}
        .topbar {{ position:fixed;top:0;left:0;right:0;background:#23272a;color:#fff;padding:10px 0 5px 0;z-index:10;text-align:center;box-shadow:0 2px 8px #18191c; }}
        .container {{ margin:60px auto 30px auto;max-width:700px;padding:0 3vw; background:#23272a; border-radius:8px; }}
        @media (max-width: 600px) {{
            .container {{ max-width:98vw;padding:0 2vw; }}
            img[style*="max-width"] {{ max-width:98vw !important; }}
        }}
        .toplink {{ color:#fff;text-decoration:underline;font-size:11px;position:fixed;bottom:20px;right:20px;background:#0055aa;padding:6px 12px;border-radius:5px;box-shadow:0 2px 8px #18191c;z-index:10; }}
        .toplink:hover {{ background:#003366; }}
    </style>
</head>
<body>
    <div class="topbar" id="topbar">
        <b>Transcript de {html.escape(channel.name)}</b>
        <span style="font-size:13px;color:#ffe066;margin-left:10px;">Gerado em {datetime.now().strftime('%d/%m/%Y %H:%M')}</span>
    </div>
    <div class="container">
    {command_section}
    {''.join(messages) if messages else "<i>Nenhuma mensagem encontrada.</i>"}
    <br><br>
    <div style="color:#888;font-size:12px;margin-top:20px;text-align:center;">Sistema HDTZ - Transcript automático</div>
    </div>
    <a href="#topbar" class="toplink">Voltar ao topo ⬆️</a>
</body>
</html>
"""
    return discord.File(fp=io.BytesIO(html_content.encode("utf-8")), filename=f"transcript_{channel.name}.html")

class AdicionarStaffModal(discord.ui.Modal, title="HDTZ | Adicionar Staff"):
    usuario = discord.ui.TextInput(
        label="Nome ou ID do Staff",
        placeholder="⚽ Exemplo: tio_ze, @tio_ze, 123456789",
        required=True
    )

    def __init__(self, channel):
        super().__init__()
        self.channel = channel

    async def on_submit(self, interaction: discord.Interaction):
        guild = interaction.guild
        value = self.usuario.value.strip()
        member = None

        try:
            if value.isdigit():
                member = await guild.fetch_member(int(value))
            else:
                value = value.replace("<@!", "").replace("<@", "").replace(">", "")
                member = guild.get_member_named(value)

            if not member:
                raise ValueError("Membro não encontrado")

            staff_role = guild.get_role(STAFF_ROLE_ID)
            if not staff_role in member.roles:
                await interaction.response.send_message(f"**🏷 | {member.mention} não é um membro da Staff!**", ephemeral=True)
                return

            # Adicionar o staff à lista de assumidos
            ticket_assumido_por.setdefault(self.channel.id, []).append(member.id)
            # Registra no banco de dados que o staff assumiu o ticket
            registrar_staff_assumindo_ticket(self.channel.id, member.id)

            registrar_interacao(self.channel.id, member.id, "adicionado", member.id)

            await self.channel.set_permissions(member, read_messages=True, send_messages=True, attach_files=True, embed_links=True)
            await interaction.response.send_message(f"**🏷 | {member.mention} foi adicionado ao ticket!**")
            await self.channel.send(f"**🏷 | Staff {member.mention} foi adicionado ao ticket por {interaction.user.mention}**")

            async for message in self.channel.history(limit=20):
                if message.pinned and message.embeds and "HDTZ - Haxball do Tio Zé | Atendimento" in message.embeds[0].title:
                    embed = message.embeds[0]

                    staff_mentions = ', '.join(f'<@{uid}>' for uid in ticket_assumido_por[self.channel.id])

                    for field in embed.fields:
                        if "Informações do Ticket:" in field.name:
                            field_lines = field.value.split('\n')
                            for i, line in enumerate(field_lines):
                                if "Staff responsável:" in line:
                                    field_lines[i] = f"**🛡️ Staff responsável:** {staff_mentions}"
                            field.value = '\n'.join(field_lines)
                            break
                    
                    await message.edit(embed=embed)
                    break

        except ValueError as e:
            await interaction.response.send_message("**🏷 | Membro não encontrado!**", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"**🏷 | Erro ao adicionar membro: {str(e)}**", ephemeral=True)

class RemoverStaffModal(discord.ui.Modal, title="HDTZ | Remover Staff"):
    usuario = discord.ui.TextInput(
        label="Nome ou ID do Staff",
        placeholder="⚽ Exemplo: tio_ze, @tio_ze, 123456789",
        required=True
    )

    def __init__(self, channel):
        super().__init__()
        self.channel = channel

    async def on_submit(self, interaction: discord.Interaction):
        guild = interaction.guild
        value = self.usuario.value.strip()
        member = None

        try:
            if value.isdigit():
                member = await guild.fetch_member(int(value))
            else:
                value = value.replace("<@!", "").replace("<@", "").replace(">", "")
                member = guild.get_member_named(value)

            if not member:
                raise ValueError("Membro não encontrado")

            staff_role = guild.get_role(STAFF_ROLE_ID)
            if not staff_role in member.roles:
                await interaction.response.send_message(f"**🏷 | {member.mention} não é um membro da Staff!**", ephemeral=True)
                return

            if self.channel.id in ticket_assumido_por and member.id in ticket_assumido_por[self.channel.id]:
                ticket_assumido_por[self.channel.id].remove(member.id)

            await self.channel.set_permissions(member, overwrite=None)
            await interaction.response.send_message(f"**🏷 | {member.mention} foi removido do ticket!**")
            await self.channel.send(f"**🏷 | Staff {member.mention} foi removido do ticket por {interaction.user.mention}**")

            async for message in self.channel.history(limit=20):
                if message.pinned and message.embeds and "HDTZ - Haxball do Tio Zé | Atendimento" in message.embeds[0].title:
                    embed = message.embeds[0]

                    staff_mentions = ', '.join(f'<@{uid}>' for uid in ticket_assumido_por[self.channel.id]) if self.channel.id in ticket_assumido_por and ticket_assumido_por[self.channel.id] else "**Ticket não assumido.**"
                    
                    for field in embed.fields:
                        if "Informações do Ticket:" in field.name:
                            field_lines = field.value.split('\n')
                            for i, line in enumerate(field_lines):
                                if "Staff responsável:" in line:
                                    field_lines[i] = f"**🛡️ Staff responsável:** {staff_mentions}"
                            field.value = '\n'.join(field_lines)
                            break
                    
                    await message.edit(embed=embed)
                    break

        except ValueError:
            await interaction.response.send_message("**❌ | Membro não encontrado!**", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"**❌ | Erro ao remover membro: {str(e)}**", ephemeral=True)

class AdicionarMembroModal(discord.ui.Modal, title="HDTZ | Adicionar membro"):
    usuario = discord.ui.TextInput(
        label="Nome ou ID",
        placeholder="⚽ Exemplo: tio_ze, @tio_ze, 123456789",
        required=True
    )

    def __init__(self, channel, author_id):
        super().__init__()
        self.channel = channel
        self.author_id = author_id

    async def on_submit(self, interaction: discord.Interaction):
        guild = interaction.guild
        value = self.usuario.value.strip()
        member = None

class RemoverMembroModal(discord.ui.Modal, title="HDTZ | Remover membro"):
    usuario = discord.ui.TextInput(
        label="Nome ou ID",
        placeholder="⚽ Exemplo: tio_ze, @tio_ze, 123456789",
        required=True
    )

    def __init__(self, channel):
        super().__init__()
        self.channel = channel

    async def on_submit(self, interaction: discord.Interaction):
        guild = interaction.guild
        value = self.usuario.value.strip()
        member = None

        try:
            if value.isdigit():
                member = await guild.fetch_member(int(value))
            else:
                value = value.replace("<@!", "").replace("<@", "").replace(">", "")
                member = guild.get_member_named(value)

            if not member:
                raise ValueError("Membro não encontrado")

            staff_role = guild.get_role(STAFF_ROLE_ID)
            if staff_role in member.roles:
                await interaction.response.send_message(f"**🏷 | Use a opção 'Remover Staff' para remover membros da Staff!**", ephemeral=True)
                return

            await self.channel.set_permissions(member, overwrite=None)
            await interaction.response.send_message(f"**🏷 | {member.mention} foi removido do ticket!**")
            await self.channel.send(f"**🏷 | {member.mention} foi removido do ticket por {interaction.user.mention}**")

        except ValueError:
            await interaction.response.send_message("**🏷 | Membro não encontrado!**", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"**🏷 | Erro ao remover membro: {str(e)}**", ephemeral=True)
        if value.startswith("<@") and value.endswith(">"):
            try:
                user_id = int(value.replace("<@", "").replace("!", "").replace(">", ""))
                member = guild.get_member(user_id)
            except Exception:
                member = None
        elif value.isdigit():
            member = guild.get_member(int(value))
        else:
            member = discord.utils.find(lambda m: m.name == value or m.display_name == value, guild.members)
        if not member:
            await interaction.response.send_message("**🏷 | Não foi possível localizar o usuário. Por gentileza, tente novamente utilizando o nome ou o ID.**", ephemeral=True)
            return
        await self.channel.set_permissions(member, view_channel=True, send_messages=True, read_messages=True, attach_files=True, embed_links=True)
        ticket_membros_adicionados.setdefault(self.channel.id, [])
        if member.id not in ticket_membros_adicionados[self.channel.id]:
            ticket_membros_adicionados[self.channel.id].append(member.id)
        await asyncio.sleep(1)
        await interaction.response.send_message(f"**🏷 | O usuário {member.mention} foi adicionado ao ticket com sucesso.**", ephemeral=False)

class FecharTicketModal(discord.ui.Modal, title="HDTZ | Informações de Fechamento"):
    motivo_fechar = discord.ui.TextInput(
        label="Motivo por fechar",
        placeholder="Ex: Banimento removido, problema resolvido, etc.",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=400
    )
    
    sala = discord.ui.TextInput(
        label="Sala",
        placeholder="Ex: Sala RS X5 Média",
        required=True,
        max_length=200
    )

    def __init__(self, interaction, fechar_callback):
        super().__init__()
        self.sala.default = f"Sala: "  
        
        self.interaction = interaction
        self.fechar_callback = fechar_callback

    async def on_submit(self, interaction: discord.Interaction):
        await self.fechar_callback(interaction, self)

# Modal específico para tickets VIP
class FecharTicketVipModal(discord.ui.Modal, title="HDTZ | Finalizar Ticket VIP"):
    motivo_fechar = discord.ui.TextInput(
        label="Motivo por finalizar",
        placeholder="Ex: VIP adquirido, dúvida esclarecida, problema resolvido, etc.",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=400
    )

    def __init__(self, interaction, fechar_callback):
        super().__init__()
        self.interaction = interaction
        self.fechar_callback = fechar_callback

    async def on_submit(self, interaction: discord.Interaction):
        await self.fechar_callback(interaction, self)

# Sistema de Avaliação
class ComentarioAvaliacaoModal(discord.ui.Modal, title="Comentário da Avaliação"):
    def __init__(self, ticket_id, user_id, staff_id, nota, descricao, view_instance):
        super().__init__()
        self.ticket_id = ticket_id
        self.user_id = user_id
        self.staff_id = staff_id
        self.nota = nota
        self.descricao = descricao
        self.view_instance = view_instance
    
    comentario = discord.ui.TextInput(
        label="Comentário (Opcional)",
        placeholder="Deixe um comentário sobre o atendimento (opcional)...",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=500
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        conn = sqlite3.connect('tickets.db')
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                INSERT INTO avaliacoes (ticket_id, user_id, staff_id, nota, comentario, data)
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ''', (self.ticket_id, self.user_id, self.staff_id, self.nota, self.comentario.value or None))
            
            conn.commit()
            
        except Exception as e:
            await interaction.response.send_message(f"❌ Erro ao salvar avaliação: {e}", ephemeral=True)
            return
        finally:
            conn.close()
        
        try:
            guild = interaction.client.get_guild(YOUR_GUILD_ID)
            canal_avaliacoes = guild.get_channel(AVALIACOES_CHANNEL_ID)
            staff_member = guild.get_member(int(self.staff_id))
            user_member = guild.get_member(int(self.user_id))
            
            if canal_avaliacoes:
                emoji_nota = {
                    0: "<:3Aviso:1404897049857753098>", 
                    3: "<:3Denncia:1404896911655440464>", 
                    5: "<:3Positivo:1404896790934851734>", 
                    7: "<:0Drafts:1404896554954784799>", 
                    10: "<:0Campeonato:1404896534637711431>"
                }.get(self.nota, "❓")
                
                cor_nota = {
                    0: discord.Color.red(),
                    3: discord.Color.orange(), 
                    5: discord.Color.yellow(),
                    7: discord.Color.green(),
                    10: discord.Color.gold()
                }.get(self.nota, discord.Color.blue())
                
                embed = discord.Embed(
                    title=f"<:3Estrela:1396678251086348338> Nova Avaliação - {self.descricao}",
                    color=discord.Color.from_rgb(252, 142, 0),
                    timestamp=datetime.now()
                )
                
                embed.add_field(
                    name="<:3Estatsticas:1396678248808845465> Informações",
                    value=(
                        f"**<:3Membro:1396885356334415922> Usuário:** {user_member.mention if user_member else f'ID: {self.user_id}'}\n"
                        f"**<:3Escudo:1396678244350300232> Staff:** {staff_member.mention if staff_member else f'ID: {self.staff_id}'}\n"
                        f"**<:0Formlario:1396675331817083013> Nota:** {self.nota}/10 ({self.descricao})\n"
                        f"**<:3Tick:1399108824488476782> Ticket:** `{self.ticket_id}`"
                    ),
                    inline=False
                )
                
                # Adicionar comentário se houver
                if self.comentario.value and self.comentario.value.strip():
                    embed.add_field(
                        name="<:4Mensagem:1396875577952047114> Comentário",
                        value=f"*\"{self.comentario.value.strip()}\"*",
                        inline=False
                    )
                
                embed.set_footer(text="HDTZ - Sistema de Avaliações")
                
                if user_member:
                    embed.set_thumbnail(url=user_member.display_avatar.url)
                
                await canal_avaliacoes.send(embed=embed)
                
        except Exception as e:
            print(f"Erro ao enviar avaliação para canal: {e}")
        
        # Continuar com o processo da view
        await self.view_instance.continuar_processo_avaliacao(interaction)

class AvaliacaoSelect(discord.ui.Select):
    def __init__(self, ticket_id, user_id, staffs_list, current_staff_index, guild):
        self.ticket_id = ticket_id
        self.user_id = user_id
        self.staffs_list = staffs_list
        self.current_staff_index = current_staff_index
        self.guild = guild
        
        # Obter nome do staff atual
        current_staff_id = staffs_list[current_staff_index]
        try:
            staff_id = int(current_staff_id) if isinstance(current_staff_id, str) else current_staff_id
            staff_member = guild.get_member(staff_id)
            staff_name = staff_member.display_name if staff_member else f"Staff ID: {current_staff_id}"
        except (ValueError, TypeError):
            staff_name = f"Staff ID: {current_staff_id}"
        
        options = [
            discord.SelectOption(
                label="0 - Péssimo",
                description="Atendimento muito ruim",
                emoji="<:3Aviso:1404897049857753098>",
                value="0"
            ),
            discord.SelectOption(
                label="3 - Ruim", 
                description="Atendimento abaixo do esperado",
                emoji="<:3Denncia:1404896911655440464>",
                value="3"
            ),
            discord.SelectOption(
                label="5 - Regular",
                description="Atendimento na média",
                emoji="<:3Positivo:1404896790934851734>",
                value="5"
            ),
            discord.SelectOption(
                label="7 - Bom",
                description="Atendimento bom",
                emoji="<:0Drafts:1404896554954784799>",
                value="7"
            ),
            discord.SelectOption(
                label="10 - Excelente",
                description="Atendimento excepcional",
                emoji="<:0Campeonato:1404896534637711431>",
                value="10"
            )
        ]
        
        super().__init__(
            placeholder=f"Avalie o atendimento de {staff_name}...",
            options=options,
            min_values=1,
            max_values=1
        )
    
    async def callback(self, interaction: discord.Interaction):
        nota = int(self.values[0])
        descricoes = {0: "Péssimo", 3: "Ruim", 5: "Regular", 7: "Bom", 10: "Excelente"}
        descricao = descricoes[nota]
        
        current_staff_id = self.staffs_list[self.current_staff_index]
        
        # Criar modal para comentário opcional
        modal = ComentarioAvaliacaoModal(
            self.ticket_id, 
            self.user_id, 
            current_staff_id, 
            nota, 
            descricao, 
            self.view
        )
        
        await interaction.response.send_modal(modal)

class AvaliacaoView(discord.ui.View):
    def __init__(self, ticket_id, user_id, staffs_list, current_staff_index=0, guild=None):
        super().__init__(timeout=None)
        self.ticket_id = ticket_id
        self.user_id = user_id
        self.staffs_list = staffs_list
        self.current_staff_index = current_staff_index
        self.guild = guild
        
        # Adicionar o select menu
        self.add_item(AvaliacaoSelect(ticket_id, user_id, staffs_list, current_staff_index, guild))
    
    async def continuar_processo_avaliacao(self, interaction):
        """Continua o processo após salvar a avaliação"""
        # Verificar se há mais staffs para avaliar
        if self.current_staff_index + 1 < len(self.staffs_list):
            # Próximo staff
            next_staff_id = self.staffs_list[self.current_staff_index + 1]
            
            try:
                guild = interaction.client.get_guild(YOUR_GUILD_ID) if not self.guild else self.guild
                staff_id = int(next_staff_id) if isinstance(next_staff_id, str) else next_staff_id
                next_staff_member = guild.get_member(staff_id)
                staff_name = next_staff_member.display_name if next_staff_member else f"Staff ID: {next_staff_id}"
            except (ValueError, TypeError):
                staff_name = f"Staff ID: {next_staff_id}"
            
            embed_proximo = discord.Embed(
                title="⭐ Avalie o Próximo Staff",
                description=f"Agora avalie o atendimento de: **{staff_name}**\n\nSelecione a nota no menu abaixo:",
                color=discord.Color.blue()
            )
            
            nova_view = AvaliacaoView(
                self.ticket_id, 
                self.user_id, 
                self.staffs_list, 
                self.current_staff_index + 1,
                self.guild
            )
            
            await interaction.response.edit_message(embed=embed_proximo, view=nova_view)
            
        else:
            # Finalizar avaliações
            embed_final = discord.Embed(
                title="✅ Avaliações Concluídas!",
                description="Obrigado por avaliar nosso atendimento!",
                color=discord.Color.green()
            )
            embed_final.add_field(
                name="🙏 Agradecimento",
                value="Sua opinião é muito importante para melhorarmos nosso atendimento!",
                inline=False
            )
            embed_final.set_footer(text="HDTZ - Obrigado pela avaliação!")
            
            await interaction.response.edit_message(embed=embed_final, view=None)

# Função para enviar avaliação no DM
async def enviar_avaliacao_dm(user_id, ticket_id, staffs_list, guild):
    """Envia sistema de avaliação no DM do usuário"""
    try:
        print(f"[DEBUG] enviar_avaliacao_dm - staffs_list: {staffs_list}")
        print(f"[DEBUG] Tipos dos staffs: {[type(s) for s in staffs_list]}")
        
        user = guild.get_member(user_id)
        if not user:
            print(f"Usuário {user_id} não encontrado para enviar avaliação")
            return
        
        # Verifica se o usuário é staff
        if has_staff_permissions(user, guild) or has_admin_permissions(user, guild):
            print(f"Usuário {user.display_name} (ID: {user_id}) é staff - não enviando avaliação")
            return
        
        if not staffs_list:
            print(f"Nenhum staff para avaliar no ticket {ticket_id}")
            return
        
        # Se só tem um staff
        if len(staffs_list) == 1:
            try:
                staff_id = int(staffs_list[0]) if isinstance(staffs_list[0], str) else staffs_list[0]
                staff_member = guild.get_member(staff_id)
                staff_name = staff_member.display_name if staff_member else f"Staff ID: {staffs_list[0]}"
            except (ValueError, TypeError):
                staff_name = f"Staff ID: {staffs_list[0]}"
            descricao = f"Como foi o atendimento de: **{staff_name}**?"
        else:
            # Múltiplos staffs
            try:
                staff_id = int(staffs_list[0]) if isinstance(staffs_list[0], str) else staffs_list[0]
                staff_member = guild.get_member(staff_id)
                staff_name = staff_member.display_name if staff_member else f"Staff ID: {staffs_list[0]}"
            except (ValueError, TypeError):
                staff_name = f"Staff ID: {staffs_list[0]}"
            descricao = f"Vamos avaliar cada staff!\n\nPrimeiro, como foi o atendimento de: **{staff_name}**?"
        
        embed = discord.Embed(
            title="⭐ Avalie nosso Atendimento",
            description=descricao,
            color=discord.Color.from_rgb(255, 186, 0)
        )
        
        embed.add_field(
            name="📊 Como Avaliar",
            value="Selecione a nota no menu abaixo para avaliar o atendimento:",
            inline=False
        )
        
        embed.set_footer(text="HDTZ - Sua opinião é importante!")
        
        view = AvaliacaoView(ticket_id, user_id, staffs_list, 0, guild)
        
        await user.send(embed=embed, view=view)
        print(f"Avaliação enviada para {user.display_name} (ID: {user_id})")
        
    except discord.Forbidden:
        print(f"Não foi possível enviar DM para o usuário {user_id} - DM fechado")
    except Exception as e:
        print(f"Erro ao enviar avaliação no DM: {e}")

# Classe TicketControlView corrigida
class TicketControlView(discord.ui.View):
    def __init__(self, author, motivo, datahora, channel_id):
        super().__init__(timeout=None)
        self.author = author
        self.motivo = motivo
        self.datahora = datahora
        self.channel_id = channel_id
        self.assumido_por = ticket_assumido_por.get(channel_id, [])
        if self.assumido_por:
            self.assumir_btn.disabled = True
        
        if not "apelação" in motivo.lower():
            self.remove_item(self.unban_btn)

    @discord.ui.button(
        label="Assumir",
        style=discord.ButtonStyle.success,
        emoji=discord.PartialEmoji(name="3Positivo", id=1396875464081018920),
        custom_id="ticket_control:assumir"
    )
    async def assumir_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not has_staff_permissions(interaction.user, interaction.guild) and not has_admin_permissions(interaction.user, interaction.guild):
            await interaction.response.send_message("**🏷 | Você não tem permissão para assumir este ticket.**", ephemeral=True)
            return

        # já deferimos aqui e usamos apenas 1 resposta no followup
        await interaction.response.defer(ephemeral=True)

        # Verifica se já assumiu
        if self.channel_id in ticket_assumido_por and interaction.user.id in ticket_assumido_por[self.channel_id]:
            await interaction.followup.send("**🏷 | Você já assumiu este ticket.**", ephemeral=True)
            return

        sucesso = await assumir_ticket_seguro(self.channel_id, interaction.user.id)

        if not sucesso:
            if self.channel_id in ticket_assumido_por and ticket_assumido_por[self.channel_id]:
                staff_mentions = ', '.join(f'<@{uid}>' for uid in ticket_assumido_por[self.channel_id])
                await interaction.followup.send(f"**🏷 | Este ticket já foi assumido por {staff_mentions}**", ephemeral=True)
            else:
                await interaction.followup.send("**🏷 | Não foi possível assumir este ticket. Tente novamente.**", ephemeral=True)
            return

        # Atualiza cache
        self.assumido_por = ticket_assumido_por[self.channel_id]
        self.assumir_btn.disabled = True

        # Edita a embed original em vez de mandar várias mensagens novas
        staff_mentions = ', '.join(f'<@{uid}>' for uid in self.assumido_por) if self.assumido_por else "**Ticket não assumido.**"
        embed = discord.Embed(
            title="🏷 HDTZ - Haxball do Tio Zé | Atendimento",
            description=f"Olá {self.author.mention}, seja bem-vindo! Como podemos te ajudar hoje?",
            color=discord.Color.from_rgb(255, 186, 0),
            timestamp=datetime.now()
        )
        embed.add_field(
            name="🧾 Informações do Ticket:",
            value=(
                f"**👤 Usuário:** {self.author.mention}\n"
                f"**🕒 Horário:** {self.datahora}\n"
                f"**📌 Motivo:** {self.motivo}\n"
                f"**🛡️ Staff responsável:** {staff_mentions}"
            ),
            inline=False
        )
        embed.add_field(
            name="⠀",
            value=f"{interaction.user.mention} assumiu este ticket e vai te ajudar agora 🤝",
            inline=False
        )
        embed.set_footer(text="HDTZ - Sistema de Tickets")

        # Edita a mensagem do botão em vez de criar uma nova
        await interaction.message.edit(embed=embed, view=self)

        # Apenas 1 followup final (não múltiplos)
        await interaction.followup.send(f"**🏷 | {interaction.user.mention} assumiu o ticket com sucesso!**", ephemeral=True)

        parar_monitoramento_ticket(self.channel_id)

    @discord.ui.button(
        label="Painel Staff",
        style=discord.ButtonStyle.success,
        emoji=discord.PartialEmoji(name="3Escudo", id=1396678244350300232),
        custom_id="ticket_control:painel_staff"
    )
    async def painel_staff_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        canal_id = interaction.channel.id
        
        # Verifica se é staff ou admin
        if not has_staff_permissions(interaction.user, interaction.guild) and not has_admin_permissions(interaction.user, interaction.guild):
            await interaction.response.send_message("**🏷 | Apenas a Staff tem permissão para usar este painel.**", ephemeral=True)
            return
            
        # Staff precisa assumir o ticket, admins não precisam
        staff_assumiu = interaction.user.id in ticket_assumido_por.get(canal_id, [])
        if not staff_assumiu and not has_admin_permissions(interaction.user, interaction.guild):
            await interaction.response.send_message("**🏷 | Você precisa assumir o ticket para usar o painel.**", ephemeral=True)
            return

        # Criar os botões para o painel de staff
        view = discord.ui.View(timeout=None)
        
        # Botão de Adicionar Staff
        add_staff_button = discord.ui.Button(
            style=discord.ButtonStyle.success,
            label="Adicionar Staff",
            emoji="<:3Mais:1396875479369252864>",
            custom_id="add_staff_btn"
        )
        
        # Botão de Remover Staff
        remove_staff_button = discord.ui.Button(
            style=discord.ButtonStyle.danger,
            label="Remover Staff", 
            emoji="<:3Negativo:1396875481986502677>",
            custom_id="remove_staff_btn"
        )
        
        # Botão de Adicionar Membro
        add_member_button = discord.ui.Button(
            style=discord.ButtonStyle.success,
            label="Adicionar Membro",
            emoji="<:3Mais:1396875479369252864>",
            custom_id="add_member_btn"
        )
        
        # Botão de Remover Membro
        remove_member_button = discord.ui.Button(
            style=discord.ButtonStyle.danger,
            label="Remover Membro",
            emoji="<:3Negativo:1396875481986502677>",
            custom_id="remove_member_btn"
        )
        
        close_now_button = None
        if canal_id in tickets_finalizados:
            close_now_button = discord.ui.Button(
                style=discord.ButtonStyle.danger,
                label="Fechar Agora",
                emoji="<:3Negativo:1396875481986502677>",
                custom_id="close_now_btn"
            )
        
        # Callback para o botão de adicionar staff
        async def add_staff_callback(btn_interaction):
            options_view = discord.ui.View(timeout=None)
            
            select_list_btn = discord.ui.Button(
                label="Selecionar da Lista",
                style=discord.ButtonStyle.success,
                emoji="<:0Formlario:1396675331817083013>",
                custom_id="select_list_btn"
            )
            
            # Botão para digitar manualmente
            manual_entry_btn = discord.ui.Button(
                label="Digitar Nome/ID",
                style=discord.ButtonStyle.success,
                emoji="<:3Membro:1396885356334415922>",
                custom_id="manual_entry_btn"
            )
            
            # Callback para o botão de selecionar da lista
            async def select_list_callback(list_interaction):
                staff_role = interaction.guild.get_role(STAFF_ROLE_ID)
                staff_members = [member for member in interaction.guild.members 
                                if staff_role in member.roles and 
                                member.id not in ticket_assumido_por.get(interaction.channel.id, [])]
                
                # Se não houver staffs disponíveis
                if not staff_members:
                    await list_interaction.response.send_message("**🏷 | Não há staffs disponíveis para adicionar.**", ephemeral=True)
                    return
                    
                staff_select = discord.ui.Select(
                    placeholder="Escolha um staff para adicionar",
                    options=[
                        discord.SelectOption(
                            label=f"{staff.display_name}",
                            value=str(staff.id),
                            emoji="👤"
                        ) for staff in staff_members[:25]
                    ]
                )
                
                async def staff_selected(select_interaction):
                    try:
                        selected_id = int(select_interaction.data["values"][0])
                        selected_staff = interaction.guild.get_member(selected_id)
                        
                        if not selected_staff:
                            await select_interaction.response.send_message("**🏷 | Staff não encontrado.**", ephemeral=True)
                            return
                            
                        # Adiciona o staff ao ticket
                        await interaction.channel.set_permissions(
                            selected_staff, 
                            view_channel=True, 
                            send_messages=True, 
                            read_messages=True,
                            manage_messages=True,
                            attach_files=True,
                            embed_links=True
                        )
                        
                        # Adiciona à lista de staff do ticket
                        ticket_assumido_por.setdefault(interaction.channel.id, [])
                        if selected_id not in ticket_assumido_por[interaction.channel.id]:
                            ticket_assumido_por[interaction.channel.id].append(selected_id)
                            # Registra no banco de dados que o staff assumiu o ticket
                            registrar_staff_assumindo_ticket(interaction.channel.id, selected_id)
                            # Registrar interação do staff sendo adicionado
                            registrar_interacao(interaction.channel.id, selected_id, "adicionado", selected_id)
                        
                        await (atualizar_staff_na_embed(interaction.channel))()
                        
                        # Notifica a adição
                        await select_interaction.response.send_message(f"**🏷 | {selected_staff.mention} foi adicionado como staff deste ticket.**", ephemeral=True)
                        await interaction.channel.send(f"**🏷 | {selected_staff.mention} foi adicionado como staff deste ticket por {interaction.user.mention}**")
                        
                    except Exception as e:
                        await select_interaction.response.send_message(f"**🏷 | Erro ao adicionar staff: {str(e)}**", ephemeral=True)
                
                # Define o callback do select
                staff_select.callback = staff_selected
                
                # Cria a view com o select
                select_view = discord.ui.View(timeout=None)
                select_view.add_item(staff_select)
                
                # Envia o menu de seleção
                await list_interaction.response.send_message(
                    "**🏷 | Selecione o staff que você deseja adicionar:**",
                    view=select_view,
                    ephemeral=True
                )
            
            async def manual_entry_callback(manual_interaction):
                class StaffInputModal(discord.ui.Modal, title="HDTZ | Adicionar Staff"):
                    staff_input = discord.ui.TextInput(
                        label="Digite o nome, menção ou ID do staff",
                        placeholder="Ex: tio_ze, @tio_ze, 123456789",
                        required=True,
                        max_length=100
                    )
                    
                    async def on_submit(self, submit_interaction: discord.Interaction):
                        value = self.staff_input.value.strip()
                        member = None
                        
                        try:
                            if value.startswith("<@") and value.endswith(">"):
                                user_id = int(value.replace("<@", "").replace("!", "").replace(">", ""))
                                member = interaction.guild.get_member(user_id)
                            elif value.isdigit():
                                member = interaction.guild.get_member(int(value))
                            else:
                                member = discord.utils.find(
                                    lambda m: value.lower() in m.name.lower() or value.lower() in m.display_name.lower(), 
                                    interaction.guild.members
                                )
                            
                            if not member:
                                await submit_interaction.response.send_message(
                                    "**🏷 | Não foi possível localizar este usuário. Verifique o nome/ID e tente novamente.**", 
                                    ephemeral=True
                                )
                                return

                            if member.id in ticket_assumido_por.get(interaction.channel.id, []):
                                await submit_interaction.response.send_message(
                                    f"**🏷 | {member.mention} já está adicionado como staff neste ticket.**", 
                                    ephemeral=True
                                )
                                return
                            
                            # Adiciona o staff ao ticket
                            await interaction.channel.set_permissions(
                                member, 
                                view_channel=True, 
                                send_messages=True, 
                                read_messages=True,
                                manage_messages=True,
                                attach_files=True,
                                embed_links=True
                            )
                            
                            # Adiciona à lista de staff do ticket
                            ticket_assumido_por.setdefault(interaction.channel.id, [])
                            if member.id not in ticket_assumido_por[interaction.channel.id]:
                                ticket_assumido_por[interaction.channel.id].append(member.id)
                                # Registra no banco de dados que o staff assumiu o ticket
                                registrar_staff_assumindo_ticket(interaction.channel.id, member.id)
                                # Registrar interação do staff sendo adicionado
                                registrar_interacao(interaction.channel.id, member.id, "adicionado", member.id)
                            
                            await (atualizar_staff_na_embed(interaction.channel))()
                            
                            # Notifica a adição (ephemeral para staff e visível para todos no canal)
                            await submit_interaction.response.send_message(f"**🏷 | {member.mention} foi adicionado como staff deste ticket.**", ephemeral=True)
                            await interaction.channel.send(f"**🏷 | {member.mention} foi adicionado como staff deste ticket por {interaction.user.mention}**")
                            
                        except Exception as e:
                            await submit_interaction.response.send_message(f"**🏷 | Erro ao adicionar staff: {str(e)}**", ephemeral=True)
                
                await manual_interaction.response.send_modal(StaffInputModal())
            
            # Define os callbacks dos botões
            select_list_btn.callback = select_list_callback
            manual_entry_btn.callback = manual_entry_callback
            
            options_view.add_item(select_list_btn)
            options_view.add_item(manual_entry_btn)
            
            await btn_interaction.response.send_message(
                "**🏷 | Como você deseja adicionar o staff?**",
                view=options_view,
                ephemeral=True
            )
        
        # Callback para o botão de remover staff
        async def remove_staff_callback(btn_interaction):
            # Lista staffs adicionados ao ticket
            ticket_staffs = []
            for staff_id in ticket_assumido_por.get(interaction.channel.id, []):
                staff = interaction.guild.get_member(staff_id)
                if staff and staff.id != interaction.user.id:  # Não mostrar o staff atual
                    ticket_staffs.append(staff)
            
            # Se não houver outros staffs
            if not ticket_staffs:
                await btn_interaction.response.send_message("**🏷 | Não há outros staffs para remover deste ticket.**", ephemeral=True)
                return
                
            staff_select = discord.ui.Select(
                placeholder="Escolha um staff para remover",
                options=[
                    discord.SelectOption(
                        label=f"{staff.display_name}",
                        value=str(staff.id),
                        emoji="👤"
                    ) for staff in ticket_staffs
                ]
            )
            
            async def staff_selected(select_interaction):
                try:
                    selected_id = int(select_interaction.data["values"][0])
                    selected_staff = interaction.guild.get_member(selected_id)
                    
                    if not selected_staff:
                        await select_interaction.response.send_message("**🏷 | Staff não encontrado.**", ephemeral=True)
                        return
                        
                    # Remove o staff do ticket
                    await interaction.channel.set_permissions(selected_staff, overwrite=None)
                    
                    # Remove da lista de staff do ticket
                    if selected_id in ticket_assumido_por.get(interaction.channel.id, []):
                        ticket_assumido_por[interaction.channel.id].remove(selected_id)
                    
                    # Atualiza a embed principal
                    await (atualizar_staff_na_embed(interaction.channel))()
                    
                    # Notifica a remoção
                    await select_interaction.response.send_message(f"**🏷 | {selected_staff.mention} foi removido dos staffs deste ticket.**", ephemeral=True)
                    await interaction.channel.send(f"**🏷 | {selected_staff.mention} foi removido deste ticket por {interaction.user.mention}**")
                    
                except Exception as e:
                    await select_interaction.response.send_message(f"**🏷 | Erro ao remover staff: {str(e)}**", ephemeral=True)
            
            # Define o callback do select
            staff_select.callback = staff_selected
            
            # Cria a view com o select
            select_view = discord.ui.View(timeout=None)
            select_view.add_item(staff_select)
            
            # Envia o menu de seleção
            await btn_interaction.response.send_message(
                "**🏷 | Selecione o staff que você deseja remover:**",
                view=select_view,
                ephemeral=True
            )
            
        # Callback para o botão de adicionar membro
        async def add_member_callback(btn_interaction):
            options_view = discord.ui.View(timeout=None)
            
            # Botão para selecionar da lista
            select_list_btn = discord.ui.Button(
                label="Selecionar da Lista",
                style=discord.ButtonStyle.success,
                emoji="<:3Membro:1396885356334415922>",
                custom_id="select_list_member_btn"
            )
            
            # Botão para digitar manualmente
            manual_entry_btn = discord.ui.Button(
                label="Digitar Nome/ID",
                style=discord.ButtonStyle.success,
                emoji="<:3Membro:1396885356334415922>",
                custom_id="manual_entry_member_btn"
            )
            
            # Callback para o botão de selecionar da lista
            async def select_list_callback(list_interaction):
                staff_role = interaction.guild.get_role(STAFF_ROLE_ID)
                regular_members = [member for member in interaction.guild.members 
                                if staff_role not in member.roles and 
                                member.id not in ticket_membros_adicionados.get(interaction.channel.id, []) and
                                member.id != self.author.id]
                
                display_members = sorted(regular_members, key=lambda m: m.display_name.lower())[:25]
                
                # Se não houver membros disponíveis
                if not display_members:
                    await list_interaction.response.send_message("**🏷 | Não há membros disponíveis para mostrar na lista. Use a opção de digitar o nome/ID.**", ephemeral=True)
                    return
                    
                member_select = discord.ui.Select(
                    placeholder="Escolha um membro para adicionar",
                    options=[
                        discord.SelectOption(
                            label=f"{member.display_name}",
                            value=str(member.id),
                            emoji="👤"
                        ) for member in display_members
                    ]
                )
                
                async def member_selected(select_interaction):
                    try:
                        selected_id = int(select_interaction.data["values"][0])
                        selected_member = interaction.guild.get_member(selected_id)
                        
                        if not selected_member:
                            await select_interaction.response.send_message("**🏷 | Membro não encontrado.**", ephemeral=True)
                            return
                            
                        # Adiciona o membro ao ticket
                        await interaction.channel.set_permissions(
                            selected_member, 
                            view_channel=True, 
                            send_messages=True, 
                            read_messages=True,
                            attach_files=True,
                            embed_links=True
                        )
                        
                        # Adiciona à lista de membros do ticket
                        ticket_membros_adicionados.setdefault(interaction.channel.id, [])
                        if selected_id not in ticket_membros_adicionados[interaction.channel.id]:
                            ticket_membros_adicionados[interaction.channel.id].append(selected_id)
                        
                        # Notifica a adição
                        await select_interaction.response.send_message(f"**🏷 | {selected_member.mention} foi adicionado ao ticket.**", ephemeral=True)
                        await interaction.channel.send(f"**<:3Membro:1396885356334415922> | {selected_member.mention} foi adicionado ao ticket por {interaction.user.mention}**")
                        
                    except Exception as e:
                        await select_interaction.response.send_message(f"**🏷 | Erro ao adicionar membro: {str(e)}**", ephemeral=True)
                
                # Define o callback do select
                member_select.callback = member_selected
                
                # Cria a view com o select
                select_view = discord.ui.View(timeout=None)
                select_view.add_item(member_select)
                
                # Envia o menu de seleção
                await list_interaction.response.send_message(
                    "**🏷 | Selecione o membro que você deseja adicionar:**",
                    view=select_view,
                    ephemeral=True
                )
            
            # Callback para o botão de inserir manualmente
            async def manual_entry_callback(manual_interaction):
                class MemberInputModal(discord.ui.Modal, title="HDTZ | Adicionar Membro"):
                    member_input = discord.ui.TextInput(
                        label="Digite o nome, menção ou ID do usuário",
                        placeholder="Ex: tio_ze, @tio_ze ou 123456789",
                        required=True,
                        max_length=100
                    )
                    
                    async def on_submit(self, submit_interaction: discord.Interaction):
                        value = self.member_input.value.strip()
                        member = None
                        
                        try:
                            if value.startswith("<@") and value.endswith(">"):
                                user_id = int(value.replace("<@", "").replace("!", "").replace(">", ""))
                                member = interaction.guild.get_member(user_id)
                            elif value.isdigit():
                                member = interaction.guild.get_member(int(value))
                            else:
                                member = discord.utils.find(
                                    lambda m: value.lower() in m.name.lower() or value.lower() in m.display_name.lower(), 
                                    interaction.guild.members
                                )
                            
                            if not member:
                                await submit_interaction.response.send_message(
                                    "**🏷 | Não foi possível localizar este usuário. Verifique o nome/ID e tente novamente.**", 
                                    ephemeral=True
                                )
                                return
                            
                            # Verifica se não é o autor do ticket
                            if member.id == self.author.id:
                                await submit_interaction.response.send_message(
                                    "**🏷 | O autor do ticket já tem acesso ao canal.**",
                                    ephemeral=True
                                )
                                return
                                
                            # Verifica se já está no ticket
                            if member.id in ticket_membros_adicionados.get(interaction.channel.id, []):
                                await submit_interaction.response.send_message(
                                    f"**🏷 | {member.mention} já está adicionado neste ticket.**", 
                                    ephemeral=True
                                )
                                return
                            
                            await interaction.channel.set_permissions(
                                member, 
                                view_channel=True, 
                                send_messages=True, 
                                read_messages=True,
                                attach_files=True,
                                embed_links=True
                            )
                            
                            # Adiciona à lista de membros do ticket
                            ticket_membros_adicionados.setdefault(interaction.channel.id, [])
                            if member.id not in ticket_membros_adicionados[interaction.channel.id]:
                                ticket_membros_adicionados[interaction.channel.id].append(member.id)
                            
                            await submit_interaction.response.send_message(f"**🏷 | {member.mention} foi adicionado ao ticket.**", ephemeral=True)
                            await interaction.channel.send(f"**<:3Membro:1396885356334415922> | {member.mention} foi adicionado ao ticket por {interaction.user.mention}**")
                            
                        except Exception as e:
                            await submit_interaction.response.send_message(f"**🏷 | Erro ao adicionar membro: {str(e)}**", ephemeral=True)
                
                # Mostra o modal para inserir o membro manualmente
                modal = MemberInputModal()
                modal.author = self.author  # Passa o autor do ticket para o modal
                await manual_interaction.response.send_modal(modal)
            
            # Define os callbacks dos botões
            select_list_btn.callback = select_list_callback
            manual_entry_btn.callback = manual_entry_callback
            
            # Adiciona os botões à view
            options_view.add_item(select_list_btn)
            options_view.add_item(manual_entry_btn)
            
            await btn_interaction.response.send_message(
                "**🏷 | Como você deseja adicionar o membro?**",
                view=options_view,
                ephemeral=True
            )
            
        async def remove_member_callback(btn_interaction):
            # Pega os membros adicionados ao ticket
            added_members_ids = ticket_membros_adicionados.get(interaction.channel.id, [])
            added_members = [interaction.guild.get_member(member_id) for member_id in added_members_ids]
            added_members = [m for m in added_members if m is not None]
            
            if not added_members:
                await btn_interaction.response.send_message("**🏷 | Não há membros adicionados neste ticket para remover.**", ephemeral=True)
                return
                
            member_select = discord.ui.Select(
                placeholder="Escolha um membro para remover",
                options=[
                    discord.SelectOption(
                        label=f"{member.display_name}",
                        value=str(member.id),
                        emoji="👤"
                    ) for member in added_members
                ]
            )
            
            async def member_selected(select_interaction):
                try:
                    selected_id = int(select_interaction.data["values"][0])
                    selected_member = interaction.guild.get_member(selected_id)
                    
                    if not selected_member:
                        await select_interaction.response.send_message("**🏷 | Membro não encontrado.**", ephemeral=True)
                        return
                        
                    # Remove o membro do ticket
                    await interaction.channel.set_permissions(selected_member, overwrite=None)
                    
                    # Remove da lista de membros do ticket
                    if selected_id in ticket_membros_adicionados.get(interaction.channel.id, []):
                        ticket_membros_adicionados[interaction.channel.id].remove(selected_id)
                    
                    # Notifica a remoção
                    await select_interaction.response.send_message(f"**🏷 | {selected_member.mention} foi removido do ticket.**", ephemeral=True)
                    await interaction.channel.send(f"**<:3Membro:1396885356334415922> | {selected_member.mention} foi removido do ticket por {interaction.user.mention}**")
                    
                except Exception as e:
                    await select_interaction.response.send_message(f"**🏷 | Erro ao remover membro: {str(e)}**", ephemeral=True)
            
            # Define o callback do select
            member_select.callback = member_selected
            
            # Cria a view com o select
            select_view = discord.ui.View(timeout=None)
            select_view.add_item(member_select)
            
            # Envia o menu de seleção
            await btn_interaction.response.send_message(
                "**🏷 | Selecione o membro que você deseja remover:**",
                view=select_view,
                ephemeral=True
            )
        
        # Callback para o botão de fechar agora
        async def close_now_callback(btn_interaction):
            # Usa os dados do modal já salvos quando o ticket foi finalizado
            finalizacao_info = tickets_finalizados.get(interaction.channel.id, {})
            modal_data = finalizacao_info.get("modal_data")
            
            if not modal_data:
                await btn_interaction.response.send_message("**🏷 | Erro: Dados de finalização não encontrados.**", ephemeral=True)
                return
            
            # Cancela o fechamento automático
            tickets_finalizados.pop(interaction.channel.id, None)
            
            # Obtém o autor do ticket
            get_author = get_ticket_author(interaction.channel)
            author_id = await get_author()
            author = interaction.guild.get_member(author_id)

            await btn_interaction.response.send_message("**🏷 | Gerando a transcrição e fechando o ticket em 3 segundos... Por favor, aguarde!**", ephemeral=False)
            try:
                # Determina o tipo de ticket pelo ID do canal
                ticket_type = ticket_types.get(interaction.channel.id)
                
                # Ou pelo nome do canal se não estiver armazenado
                if not ticket_type:
                    channel_name = interaction.channel.name
                    if "ap-" in channel_name:
                        ticket_type = "apelação"
                    elif "rep-" in channel_name:
                        ticket_type = "Denúncia"
                    else:
                        ticket_type = "suporte"
                
                transcript_channel_id = TRANSCRIPT_CHANNELS.get(ticket_type, TRANSCRIPT_CHANNEL_ID)
                transcript_channel = interaction.guild.get_channel(transcript_channel_id)
                
                if transcript_channel:
                    file = await gerar_transcript_html(interaction.channel)
                    embed = discord.Embed(
                        title=f"{TICKET_EMOJIS.get(ticket_type, '🎫')} Detalhes do Fechamento do Ticket ({ticket_type.capitalize() if ticket_type else 'Desconhecido'})",
                        color=discord.Color.from_rgb(255, 186, 0),
                        timestamp=datetime.now()
                    )
                    embed.add_field(name="Motivo por fechar", value=modal_data["motivo_fechar"], inline=False)
                    if "sala" in modal_data:
                        embed.add_field(name="Sala", value=modal_data["sala"], inline=False)
                    embed.set_footer(text="HDTZ - Sistema de Tickets")
    
                    await transcript_channel.send(
                        f"**📝 | Transcript do ticket `{interaction.channel.name}` fechado por {btn_interaction.user.mention}:**\n**TicketID:** `{author_id}`",
                        embed=embed,
                        file=file
                    )
                
            except Exception as e:
                print(f"Erro ao enviar transcript: {e}")
                
            fechar_ticket(interaction.channel.id, btn_interaction.user.id)
            
            parar_monitoramento_ticket(interaction.channel.id)
            
            await asyncio.sleep(3)
            await interaction.channel.delete()
            
            ticket_assumido_por.pop(interaction.channel.id, None)
            ticket_membros_adicionados.pop(interaction.channel.id, None)
            ticket_types.pop(interaction.channel.id, None)
        
        # Associa callbacks aos botões
        add_staff_button.callback = add_staff_callback
        remove_staff_button.callback = remove_staff_callback
        add_member_button.callback = add_member_callback
        remove_member_button.callback = remove_member_callback
        if close_now_button:
            close_now_button.callback = close_now_callback
        
        # Adiciona os botões à view
        view.add_item(add_staff_button)
        view.add_item(remove_staff_button)
        view.add_item(add_member_button)
        view.add_item(remove_member_button)
        if close_now_button:
            view.add_item(close_now_button)
        
        # Cria a embed do painel
        embed = discord.Embed(
            title="HDTZ - Haxball do Tio Zé | Painel Staff",
            description=f"👋 Olá {interaction.user.mention}, bem-vindo ao painel de staff. Escolha uma opção abaixo:",
            color=discord.Color.from_rgb(255, 186, 0)
        )

        embed.add_field(
            name="📌 Gerenciamento de Staff",
            value=(
                "**Adicionar Staff:** Permite incluir outro staff\n"
                "**Remover Staff:** Remove um staff adicionado ao ticket"
            ),
            inline=False
        )
        
        embed.add_field(
            name="👥 Gerenciamento de Membros",
            value=(
                "**Adicionar Membro:** Inclui outro membro no ticket\n"
                "**Remover Membro:** Remove um membro do ticket"
            ),
            inline=False
        )
        
        if canal_id in tickets_finalizados:
            finalizacao_info = tickets_finalizados[canal_id]
            tempo_fechamento = finalizacao_info["timestamp"] + timedelta(hours=12)
            embed.add_field(
                name="⚠️ Ticket Finalizado",
                value=(
                    f"**Fechamento automático:** <t:{int(tempo_fechamento.timestamp())}:R>\n"
                    f"**Fechar Agora:** Use o botão para fechar antes do prazo"
                ),
                inline=False
            )
        
        embed.set_footer(text="HDTZ - Sistema de Tickets")
        
        # Envia o painel
        await interaction.response.send_message(
            embed=embed,
            view=view,
            ephemeral=True
        )

    @discord.ui.button(
        label="Unban",
        style=discord.ButtonStyle.danger,
        emoji=discord.PartialEmoji(name="3Banimento", id=1396678181741662353),
        custom_id="ticket_control:unban"
    )
    async def unban_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Verifica se é um ticket de apelação
        if "apelação" not in self.motivo.lower():
            await interaction.response.send_message("**🏷 | Este botão só pode ser usado em tickets de apelação.**", ephemeral=True)
            return

        # Verifica se é staff
        if not can_use_advanced_features(interaction.user, interaction.guild):
            await interaction.response.send_message("**🏷 | Apenas administradores podem usar este botão.**", ephemeral=True)
            return

        # Verifica se o staff assumiu o ticket
        if interaction.user.id not in ticket_assumido_por.get(self.channel_id, []) and interaction.user.id not in ALLOWED_USER_IDS:
            await interaction.response.send_message("**🏷 | Apenas o staff que assumiu este ticket pode usar o botão Unban.**", ephemeral=True)
            return

        # Verifica o cooldown
        user_id = interaction.user.id
        current_time = datetime.now(timezone.utc)
        last_use = unban_cooldown.get(user_id)
        
        if last_use:
            time_passed = (current_time - last_use).total_seconds()
            if time_passed < 180: 
                remaining = int(180 - time_passed)
                minutes = remaining // 60
                seconds = remaining % 60
                await interaction.response.send_message(
                    f"**🕒 | Aguarde {minutes}min e {seconds}s para usar este botão novamente.**",
                    ephemeral=True
                )
                return
        
        # Atualiza o cooldown
        unban_cooldown[user_id] = current_time

        # Envia a mensagem com as informações do unban
        await interaction.response.send_message(
            "**<:3Estrela:1396678251086348338> MULTA HDTZ <:3Estrela:1396678251086348338>**\n\n"
            "> Foi banido por nível ou por toxicidade? Agora tem multa!\n"
            "> Quanto mais repetir, mais caro fica!\n\n"
            "**<:3Banimento:1396678181741662353> Nível:**\n"
            "1ª vez: R$1,50 | 2ª vez: R$3,00 | 3ª vez ou mais: R$4,50\n\n"
            "**<:52Toxico:1396609701562810419> Toxicidade:**\n"
            "1ª vez: R$3,00 | 2ª vez: R$6,00 | 3ª vez ou mais: R$9,00\n\n"
            "**<:52Toxico:1396609701562810419> Toxicidade Grave**\n"
            "1ª vez: R$5,00 | 2ª vez: R$10,00 | 3ª vez ou mais: R$15,00\n\n"
            "> <:3Substituio:1396875469915160776> As multas são resetadas todo dia 1º do mês\n"
            "> <:3Denncia:1396678232413310987> Ban por racismo ou evasão não tem direito a multa!\n\n"
            "**<:3Carto:1396678216734867637> Chave Pix: 10.368.717/0001-44**\n\n"
            "**<:4Mensagem:1396875577952047114> Após o pagamento, envie o comprovante diretamente aqui no chat.**",
            ephemeral=False
        )

    @discord.ui.button(
        label="Finalizar",
        style=discord.ButtonStyle.danger,
        emoji=discord.PartialEmoji(name="3Negativo", id=1396875481986502677),
        custom_id="ticket_control:finalizar"
    )
    async def finalizar_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        staff_role = interaction.guild.get_role(STAFF_ROLE_ID)
        quem_assumiu = ticket_assumido_por.get(self.channel_id, [])
        if not has_staff_permissions(interaction.user, interaction.guild) and not has_admin_permissions(interaction.user, interaction.guild):
            await interaction.response.send_message("**🏷 | Apenas a Staff tem permissão para finalizar os tickets.**", ephemeral=True)
            return

        if quem_assumiu and interaction.user.id not in quem_assumiu and interaction.user.id not in ALLOWED_USER_IDS and not has_admin_permissions(interaction.user, interaction.guild):
            staff_mentions = ', '.join(f'<@{uid}>' for uid in quem_assumiu)
            await interaction.response.send_message(f"**🏷 | Apenas o membro da Staff que assumiu este ticket pode finalizá-lo: {staff_mentions}**", ephemeral=True)
            return

        # Verifica se o ticket já foi finalizado
        if self.channel_id in tickets_finalizados:
            await interaction.response.send_message("**🏷 | Este ticket já foi finalizado e será fechado automaticamente em breve.**", ephemeral=True)
            return
        
        conn = sqlite3.connect('tickets.db')
        cursor = conn.cursor()
        try:
            cursor.execute('SELECT status FROM tickets WHERE ticket_id = ?', (str(self.channel_id),))
            ticket_status = cursor.fetchone()
            if ticket_status and ticket_status[0] == 'fechado':
                await interaction.response.send_message("**🏷 | Este ticket já foi fechado no sistema.**", ephemeral=True)
                return
        except Exception as e:
            print(f"[ERROR] Erro ao verificar status do ticket: {e}")
        finally:
            conn.close()

        if not quem_assumiu:
            print(f"[INFO] Ticket {self.channel_id} não foi assumido por ninguém, qualquer staff pode finalizar.")

        # Callback para quando o modal for enviado
        async def finalizar_callback(modal_interaction, modal):
            author = self.author

            try:
                current_name = interaction.channel.name
                if not current_name.endswith("-finalizado"):
                    new_name = current_name + "-finalizado"
                    await interaction.channel.edit(name=new_name)
                    print(f"[FINALIZAR] Canal renomeado de '{current_name}' para '{new_name}'")
            except Exception as e:
                print(f"[ERROR] Erro ao renomear canal para finalizado: {e}")
            
            await interaction.channel.set_permissions(
                author, 
                view_channel=True,      
                read_messages=True,     
                send_messages=False,    
                attach_files=False,     
                embed_links=False       
            )
            
            staff_role = interaction.guild.get_role(STAFF_ROLE_ID)
            membros_adicionados_ids = ticket_membros_adicionados.get(self.channel_id, [])
            
            for membro_id in membros_adicionados_ids:
                membro = interaction.guild.get_member(membro_id)
                if membro and not has_staff_permissions(membro, interaction.guild) and not has_admin_permissions(membro, interaction.guild):  # Só remove permissão se não for staff nem admin
                    await interaction.channel.set_permissions(
                        membro,
                        view_channel=True,      
                        read_messages=True,     
                        send_messages=False,    
                        attach_files=False,     
                        embed_links=False      
                    )

            mensagem_avaliacao = RESPOSTAS_PREDEFINIDAS.get("form")
            
            ticket_type = ticket_types.get(self.channel_id, "")
            if ticket_type == "VIPs":
                modal_data = {
                    "motivo_fechar": modal.motivo_fechar.value
                }
            else:
                modal_data = {
                    "motivo_fechar": modal.motivo_fechar.value,
                    "sala": modal.sala.value
                }
            
            # Adiciona o ticket à lista de finalizados
            tickets_finalizados[self.channel_id] = {
                "staff_id": interaction.user.id,
                "timestamp": datetime.now(),
                "guild": interaction.guild,
                "modal_data": modal_data
            }
            
            asyncio.create_task(fechar_ticket_automatico(self.channel_id, interaction.guild, delay_seconds=43200))  # 12 horas = 43200 segundos

            self.finalizar_btn.disabled = True
            
            parar_monitoramento_ticket(self.channel_id)
            
            try:
                # Buscar staffs que participaram deste ticket
                conn = sqlite3.connect('tickets.db')
                cursor = conn.cursor()
                
                cursor.execute('''
                    SELECT DISTINCT staff_id FROM interacoes 
                    WHERE ticket_id = ? AND staff_id IS NOT NULL
                ''', (self.channel_id,))
                
                staffs_participantes = [row[0] for row in cursor.fetchall()]
                
                # Se não há staffs nas interações, usar fallbacks
                if not staffs_participantes:
                    # Fallback 1: Staffs que estão assumindo o ticket atualmente
                    staffs_assumindo = ticket_assumido_por.get(self.channel_id, [])
                    if staffs_assumindo:
                        staffs_participantes = list(set(staffs_assumindo))  # Remove duplicatas
                        print(f"Usando staffs assumindo ticket para avaliação: {staffs_participantes}")
                    else:
                        # Fallback 2: Buscar quem finalizou o ticket na tabela tickets
                        cursor.execute('''
                            SELECT finalizador_id FROM tickets 
                            WHERE ticket_id = ? AND finalizador_id IS NOT NULL
                        ''', (self.channel_id,))
                        
                        finalizador = cursor.fetchone()
                        if finalizador:
                            staffs_participantes = [finalizador[0]]
                            print(f"Usando finalizador como staff para avaliação: {finalizador[0]}")

                conn.close()
                
                # Se há staffs para avaliar e temos um autor válido
                if staffs_participantes and hasattr(self, 'author') and self.author:
                    print(f"Enviando avaliação para ticket {self.channel_id} - Staffs: {staffs_participantes}")
                    print(f"Tipos dos IDs: {[type(staff_id) for staff_id in staffs_participantes]}")
                    asyncio.create_task(enviar_avaliacao_dm(
                        self.author.id, 
                        self.channel_id, 
                        staffs_participantes, 
                        interaction.guild
                    ))
                else:
                    print(f"Não foi possível enviar avaliação para ticket {self.channel_id}")
                    print(f"- Staffs participantes: {staffs_participantes}")
                    print(f"- Autor do ticket: {getattr(self, 'author', 'Não encontrado')}")
                    
            except Exception as e:
                print(f"Erro ao enviar sistema de avaliação: {e}")
            
            # Envia a resposta
            membros_sem_permissao = [author.mention]
            for membro_id in membros_adicionados_ids:
                membro = interaction.guild.get_member(membro_id)
                if membro and not has_staff_permissions(membro, interaction.guild) and not has_admin_permissions(membro, interaction.guild):
                    membros_sem_permissao.append(membro.mention)
            
            mensagem_membros = ", ".join(membros_sem_permissao) if len(membros_sem_permissao) > 1 else author.mention
            
            await modal_interaction.response.send_message(
                f"**🏷 | Ticket finalizado por {interaction.user.mention}!**\n\n"
                f"<:0Formlario:1396675331817083013>  **O ticket será fechado automaticamente em 12 horas.**\n"
                f"<:3Relogio:1396875467218489344>  **Fechamento programado para:** <t:{int((datetime.now() + timedelta(hours=12)).timestamp())}:F>\n\n"
                f"<:3Aviso:1397810681172201502> **{mensagem_membros} não {'podem' if len(membros_sem_permissao) > 1 else 'pode'} mais enviar mensagens neste ticket.**\n\n"
            )


            class AvaliarAgoraView(discord.ui.View):
                def __init__(self, author, staffs_participantes, channel_id, guild):
                    super().__init__(timeout=None)
                    self.author = author
                    self.staffs_participantes = staffs_participantes
                    self.channel_id = channel_id
                    self.guild = guild


                @discord.ui.button(
                    label="Avaliar Agora",
                    style=discord.ButtonStyle.primary,
                    emoji=discord.PartialEmoji(name="3Estrela", id=1396675331817083013),
                    custom_id="evaluate_now_btn"
                )       
                async def avaliar_agora_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
                    if interaction.user.id != self.author.id:
                        await interaction.response.send_message("Este botão só pode ser usado pelo autor do ticket.", ephemeral=True)
                        return
                    await enviar_avaliacao_dm(self.author.id, self.channel_id, self.staffs_participantes, self.guild)
                    await interaction.response.send_message("O sistema de avaliação foi enviado na sua DM!", ephemeral=True)

            embed_extra = discord.Embed(
                title="Avalie nosso Atendimento",
                description=(
                f"Olá {author.mention}\n\n"
                f"Você tem **{len(staffs_participantes)}** {'membros da Staff' if len(staffs_participantes) > 1 else 'membro da Staff'} para avaliar!\n\n"
                "📋 Como funciona:\n"
                "• Sua avaliação ficará pendente até ser concluída\n"
                "• Para abrir um novo ticket, você precisa avaliar todos os staffs pendentes\n"
                "• Use o botão abaixo para avaliar agora ou avalie depois ao tentar abrir um novo ticket\n"
                "• Isso nos ajuda a melhorar cada vez mais nosso atendimento!"

 ),
        color=discord.Color.from_rgb(255, 186, 0),
        timestamp=datetime.now(timezone.utc)
            )
            embed_extra.set_footer(text="HDTZ 2025 - Todos os direitos reservados!")
            await interaction.channel.send(embed=embed_extra)
        


        ticket_type = ticket_types.get(self.channel_id, "")
        if ticket_type == "VIPs":
            modal = FecharTicketVipModal(interaction, finalizar_callback)
        else:
            modal = FecharTicketModal(interaction, finalizar_callback)
            
        await interaction.response.send_modal(modal)

class TicketSelectView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        
        # Adicionar o select menu
        self.add_item(TicketSelect())

class TicketSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(
                label="Suporte",
                description="Tire suas dúvidas e resolva problemas",
                emoji=discord.PartialEmoji(name="3Suporte", id=1396875471651737612),
                value="suporte"
            ),
            discord.SelectOption(
                label="Denúncia",
                description="Reporte comportamentos inadequados",
                emoji=discord.PartialEmoji(name="3Denncia", id=1396678232413310987),
                value="Denúncia"
            ),
            discord.SelectOption(
                label="Apelação",
                description="Conteste punições aplicadas",
                emoji=discord.PartialEmoji(name="3Banimento", id=1396678181741662353),
                value="apelação"
            ),
            discord.SelectOption(
                label="VIP",
                description="Atendimento exclusivo e vendas de VIP",
                emoji=discord.PartialEmoji(name="50Vip", id=1396609696332255344),
                value="VIPs"
            )
        ]
        
        super().__init__(
            placeholder="🎫 Selecione o motivo do seu contato...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="ticket_select:main"
        )
    
    async def callback(self, interaction: discord.Interaction):
        motivo = self.values[0]
        await self.create_ticket(interaction, motivo)
    
    async def create_ticket(self, interaction: discord.Interaction, motivo: str):
        user_id = interaction.user.id
        now = datetime.now().timestamp()
        
        if user_id in ticket_creation_cooldown:
            time_left = TICKET_COOLDOWN_SECONDS - (now - ticket_creation_cooldown[user_id])
            if time_left > 0:
                try:
                    await interaction.response.send_message(
                        f"**⏰ | Aguarde {int(time_left)} segundos antes de criar outro ticket.**",
                        ephemeral=True
                    )
                except:
                    pass
                return
        
        # Registrar o timestamp atual
        ticket_creation_cooldown[user_id] = now
        
        if motivo == "VIPs":
            initial_message = "**👑 | A HDTZ está criando seu ticket VIP, aguarde alguns segundos...**"
        else:
            initial_message = "**🏷 | A HDTZ está criando seu ticket, aguarde alguns segundos...**"
        
        try:
            await interaction.response.send_message(initial_message, ephemeral=True)
        except discord.InteractionResponded:
            try:
                await interaction.followup.send(initial_message, ephemeral=True)
            except:
                pass
        except Exception as e:
            print(f"[ERROR] Falha ao responder interação: {e}")
        
        guild = interaction.guild
        author = interaction.user

        try:
            if await user_ticket_count(guild, author) >= MAX_TICKETS_PER_USER:
                await interaction.followup.send("**🏷 | Você já atingiu o limite de 2 tickets abertos. Feche um ticket antes de abrir outro.**", ephemeral=True)
                return
        except Exception as e:
            print(f"[ERROR] Erro ao verificar limite de tickets: {e}")
            return

        user_name = ''.join(c for c in author.display_name.lower() if c.isalnum() or c in ['-', '_'])
        user_name = user_name[:15]
        
        base_name = f"🎫・{user_name}"
        channel_name = base_name
        
        existing_channels = [c.name for c in guild.text_channels if c.name.startswith(f"🎫・{user_name}")]
        
        if base_name in existing_channels:
            count = 1
            while True:
                count += 1
                channel_name = f"🎫・{user_name}-{count}"
                if channel_name not in existing_channels:
                    break

        existing = discord.utils.get(guild.channels, name=channel_name)
        if existing:
            try:
                await interaction.followup.send(f"**🏷 | Você já tem um ticket aberto: {existing.mention}**", ephemeral=True)
            except:
                pass
            return

        # Usar as categorias corretas
        category_id = CATEGORY_IDS.get(motivo) or CATEGORY_IDS.get("suporte")  # Fallback para suporte
        category = discord.utils.get(guild.categories, id=category_id) if category_id else None
        
        if not category:
            try:
                await interaction.followup.send("**🏷 | Categoria não configurada. Entre em contato com a administração.**", ephemeral=True)
            except:
                pass
            return

        # Configurar permissões
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            author: discord.PermissionOverwrite(
                view_channel=True, send_messages=True, read_message_history=True,
                attach_files=True, embed_links=True, use_external_emojis=True
            ),
            guild.me: discord.PermissionOverwrite(
                view_channel=True, send_messages=True, read_message_history=True,
                manage_messages=True, embed_links=True, attach_files=True
            )
        }

        # Adicionar permissões para staff
        staff_role = guild.get_role(STAFF_ROLE_ID)
        if staff_role:
            overwrites[staff_role] = discord.PermissionOverwrite(
                view_channel=True, send_messages=True, read_message_history=True,
                manage_messages=True, embed_links=True, attach_files=True
            )

        try:
            channel = await guild.create_text_channel(channel_name, category=category, overwrites=overwrites)
            
            if motivo == "VIPs":
                success_message = "**👑 | Ticket VIP criado! Clique no botão abaixo para acessar!**"
                button_label = "Ir ao Ticket VIP"
                button_emoji = "👑"
            else:
                success_message = "**🏷️ | Ticket criado! Clique no botão abaixo para acessar!**"
                button_label = "Ir ao Ticket"
                button_emoji = "🎫"
            
            success = False
            try:
                await interaction.edit_original_response(
                    content=success_message,
                    view=discord.ui.View().add_item(
                        discord.ui.Button(
                            style=discord.ButtonStyle.url,
                            label=button_label,
                            emoji=button_emoji,
                            url=channel.jump_url
                        )
                    )
                )
                success = True
            except:
                pass
            
            if not success:
                try:
                    await interaction.followup.send(
                        f"**🏷️ | Ticket criado com sucesso! Acesse: {channel.mention}**",
                        ephemeral=True
                    )
                except Exception as e:
                    print(f"[ERROR] Falha total ao enviar resposta: {e}")
                    # Mesmo se falhar a resposta, o canal foi criado

        except discord.HTTPException as e:
            print(f"[ERROR] Erro ao criar canal: {e}")
            try:
                await interaction.followup.send("**🏷 | Erro ao criar o ticket. Tente novamente em alguns segundos.**", ephemeral=True)
            except:
                print("[ERROR] Falha ao enviar mensagem de erro")
            return
        except Exception as e:
            print(f"[ERROR] Erro inesperado: {e}")
            try:
                await interaction.followup.send("**🏷 | Erro inesperado. Entre em contato com a administração.**", ephemeral=True)
            except:
                print("[ERROR] Falha ao enviar mensagem de erro inesperado")
            return

        ticket_types[channel.id] = motivo
        
        # Registra o ticket no banco de dados
        registrar_ticket(channel.id, author.id, motivo)

        now = datetime.now(timezone.utc)
        hour_br = (now.hour - 3) % 24
        datahora = now.replace(hour=hour_br).strftime("%d/%m/%Y | %H:%M:%S")

        motivo_formatado = motivo.capitalize() if motivo != "Denúncia" else "Denúncia"
        emoji = TICKET_EMOJIS.get(motivo, "🎫")

        ticket_assumido_por[channel.id] = []

        embed = discord.Embed(
            title="🏷 HDTZ - Haxball do Tio Zé | Atendimento",
            description=f"Olá {author.mention}, seja bem-vindo! Como podemos te ajudar hoje?",
            color=discord.Color.from_rgb(255, 186, 0),
            timestamp=datetime.now()
        )
        embed.add_field(
            name="🧾 Informações do Ticket:",
            value=(
                f"**👤 Usuário:** {author.mention}\n"
                f"**🕒 Horário:** {datahora}\n"
                f"**📌 Motivo:** {emoji} {motivo_formatado}\n"
                f"**🛡️ Staff responsável:** Ticket não assumido."
            ),
            inline=False
        )
        embed.add_field(
            name="⠀",
            value=(
                f"Bom {author.mention}, pedimos que aguarde pacientemente.\n\n"
                f"Nossa equipe já foi acionada e em breve alguém irá te atender. 🤝"
            ),
            inline=False
        )
        embed.set_footer(text="HDTZ - Sistema de Tickets")

        view = TicketControlView(author, f"{emoji} {motivo_formatado}", datahora, channel.id)
        
        initial_message = await channel.send(embed=embed, view=view)
        
        await channel.send(f"||{author.mention} {guild.get_role(STAFF_ROLE_ID).mention}||", 
                          allowed_mentions=discord.AllowedMentions(roles=True, users=True))
        
        await initial_message.pin()
        
        await iniciar_monitoramento_ticket(channel.id, guild)


def atualizar_staff_na_embed(channel):
    async def inner():
        staffs_atuais = ticket_assumido_por.get(channel.id, [])
        staffs_mencoes = [f"<@{uid}>" for uid in staffs_atuais] if staffs_atuais else ["Ticket não assumido."]
        async for msg in channel.history(limit=20, oldest_first=True):
            if msg.embeds:
                embed = msg.embeds[0]
                for i, field in enumerate(embed.fields):
                    if "Staff responsável:" in field.value:
                        novo_valor = field.value.replace(
                            field.value.split("Staff responsável:")[1],
                            f" {', '.join(staffs_mencoes)}"
                        )
                        embed.set_field_at(
                            i, 
                            name=field.name,
                            value=novo_valor,
                            inline=field.inline
                        )
                        await msg.edit(embed=embed)
                        return
    return inner

@bot.tree.command(name="gerar-painel", description="[🔧] Gera o Painel de Tickets HDTZ")
@app_commands.default_permissions(manage_channels=True)
async def painelticket(interaction: discord.Interaction):
    """Comando para criar painel de tickets com select menu"""
    # Verifica se o usuário tem permissão de adm
    if not can_use_advanced_features(interaction.user, interaction.guild):
        await interaction.response.send_message("**🏷 | Apenas administradores podem criar painéis.**", ephemeral=True)
        return
    
    # Painel HDTZ com Select Menu
    embed = discord.Embed(
        title="<:3Escudo:1396678244350300232> Centro de Atendimento HDTZ",
        description=(
            "Bem-vindo ao sistema de tickets da HDTZ — o atendimento mais rápido do Haxball!\n\n"
            "**Selecione o motivo do seu contato no menu abaixo:**\n"
            "<:3Suporte:1396875471651737612> **Suporte** - Tire suas dúvidas e resolva problemas\n"
            "<:3Denncia:1396678232413310987> **Denúncia** - Reporte comportamentos inadequados\n"
            "<:3APL:1399110778832814141> **Apelação** - Conteste punições aplicadas\n"
            "<:50Vip:1396609696332255344> **VIP** - Atendimento exclusivo e aquisição de VIP\n\n"
            "Após selecionar, será criado um canal privado só com você e a equipe.\n"
            "Lá, poderemos te atender de forma rápida, segura e organizada."
        ),
        color=discord.Color.from_rgb(255, 186, 0)
    )
    embed.set_image(url="https://i.ibb.co/nqGgSYyr/ticket.png")
    
    await interaction.channel.send(embed=embed, view=TicketSelectView())
    await interaction.response.send_message("**🎫 | Painel de tickets criado com sucesso!**", ephemeral=True)




@bot.tree.command(name="resposta", description="[🔧] Envia uma resposta predefinida")
@app_commands.default_permissions(manage_channels=True)
@app_commands.describe(tipo="Tipo de resposta a ser enviada")
@app_commands.choices(tipo=[
    app_commands.Choice(name="VIP", value="vip"),
    app_commands.Choice(name="Unban", value="unban"),
    app_commands.Choice(name="Parceria", value="parceria"),
    app_commands.Choice(name="Form", value="form")
])
async def resposta(interaction: discord.Interaction, tipo: str):
    # Verifica se é um canal de ticket
    if not isinstance(interaction.channel, discord.TextChannel) or not interaction.channel.name.startswith("🎫・"):
        await interaction.response.send_message("**🏷 | Este comando só pode ser usado em canais de ticket.**", ephemeral=True)
        return
    
    # Verifica se quem usou é staff ou adm
    if not has_staff_permissions(interaction.user, interaction.guild) and not has_admin_permissions(interaction.user, interaction.guild):
        await interaction.response.send_message("**🏷 | Apenas membros da Staff podem usar este comando.**", ephemeral=True)
        return
    
    # Verifica se o staff assumiu o ticket
    channel_id = interaction.channel.id
    if interaction.user.id not in ticket_assumido_por.get(channel_id, []):
        await interaction.response.send_message("**🏷 | Você precisa assumir o ticket para usar respostas rápidas.**", ephemeral=True)
        return
    
    # Envia a resposta predefinida
    resposta = RESPOSTAS_PREDEFINIDAS.get(tipo.lower())
    if resposta:
        await interaction.response.send_message(resposta)
    else:
        await interaction.response.send_message("**🏷 | Tipo de resposta não encontrado.**", ephemeral=True)

@bot.tree.command(name="rank", description="[🔧] Mostra o rank de tickets abertos e assumidos")
@app_commands.default_permissions(manage_channels=True)
@app_commands.describe(
    tipo="Escolha o tipo de ranking que deseja visualizar"
)
@app_commands.choices(tipo=[
    app_commands.Choice(name="👑 Membros que mais abriram tickets", value="membro"),
    app_commands.Choice(name="👑 Staffs que mais assumiram tickets", value="staff")
])
async def rankticket(interaction: discord.Interaction, tipo: str):
    """Comando para mostrar ranking de tickets"""
    # Verifica se o usuário tem permissão de admin
    if not can_use_advanced_features(interaction.user, interaction.guild):
        await interaction.response.send_message("**🏷 | Apenas administradores podem ver os rankings.**", ephemeral=True)
        return
    
    if tipo == "membro":
        ranking = obter_ranking_tickets_abertos()
        
        embed = discord.Embed(
            title="HDTZ - Haxball do Tio Zé | Ranking",
            description=":trophy:・`TOP 15 DE QUEM MAIS ABRIU TICKET.`",
            color=discord.Color.from_rgb(255, 186, 0),
            timestamp=datetime.now()
        )
        
        if interaction.guild.icon:
            embed.set_author(name=interaction.guild.name, icon_url=interaction.guild.icon.url)
        
        embed.set_thumbnail(url="https://cdn.discordapp.com/attachments/1392962805472170207/1400983692938076160/Design_sem_nome_5.png")
        
        if not ranking:
            embed.add_field(
                name="📊 Ranking",
                value="**Nenhum dado encontrado.**",
                inline=False
            )
        else:
            # Mostra os 15 primeiros
            ranking_limitado = ranking[:15]
            ranking_texto = []
            emojis = ["🥇", "🥈", "🥉"] + ["🏅"] * 12
            
            for i, (user_id, quantidade) in enumerate(ranking_limitado, 1):
                try:
                    user = interaction.guild.get_member(int(user_id))
                    if user:
                        nome = user.mention
                    else:
                        nome = f"ID: {str(user_id)[:10]}"
                    
                    emoji = emojis[i-1] if i <= len(emojis) else "🏅"
                    ranking_texto.append(f"{emoji} **{i}º** {nome}: `{quantidade}`")
                except:
                    ranking_texto.append(f"🏅 **{i}º** ID: {str(user_id)[:10]}: `{quantidade}`")
            
            embed.add_field(
                name="📊 Ranking de Tickets Abertos",
                value="\n".join(ranking_texto),
                inline=False
            )
    
    elif tipo == "staff":
        ranking = obter_ranking_tickets_assumidos()
        
        embed = discord.Embed(
            title="HDTZ - Haxball do Tio Zé | Ranking Staff",
            description=":trophy:・`TOP 15 DE QUEM MAIS ASSUMIU TICKET`",
            color=discord.Color.from_rgb(255, 186, 0),
            timestamp=datetime.now()
        )
        
        if interaction.guild.icon:
            embed.set_author(name=interaction.guild.name, icon_url=interaction.guild.icon.url)
        
        embed.set_thumbnail(url="https://cdn.discordapp.com/attachments/1392962805472170207/1400983692938076160/Design_sem_nome_5.png")
        
        if not ranking:
            embed.add_field(
                name="📊 Ranking",
                value="**Nenhum dado encontrado.**",
                inline=False
            )
        else:
            ranking_limitado = ranking[:15]
            ranking_texto = []
            emojis = ["🥇", "🥈", "🥉"] + ["🛡️"] * 12
            
            for i, (staff_id, quantidade) in enumerate(ranking_limitado, 1):
                try:
                    staff = interaction.guild.get_member(int(staff_id))
                    if staff:
                        nome = staff.mention
                    else:
                        nome = f"ID: {str(staff_id)[:10]}"
                    
                    emoji = emojis[i-1] if i <= len(emojis) else "🛡️"
                    ranking_texto.append(f"{emoji} **{i}º** {nome}: `{quantidade}`")
                except:
                    ranking_texto.append(f"🛡️ **{i}º** ID: {str(staff_id)[:10]}: `{quantidade}`")
            
            embed.add_field(
                name="🛡️ Ranking de Tickets Assumidos",
                value="\n".join(ranking_texto),
                inline=False
            )
    
    embed.set_footer(text="HDTZ - Haxball do Tio Zé")
    await interaction.response.send_message(embed=embed)

# Comando para estatísticas mensais de tickets
@bot.tree.command(name="statsticket", description="[📊] Mostra estatísticas mensais de tickets por categoria")
@app_commands.default_permissions(manage_channels=True)
@app_commands.describe(
    mes="Mês para consultar (1-12, deixe vazio para mês atual)",
    ano="Ano para consultar (deixe vazio para ano atual)"
)
async def stats_ticket(interaction: discord.Interaction, mes: int = None, ano: int = None):
    """Comando para mostrar estatísticas mensais de tickets por categoria"""
    # Verifica se o usuário tem permissão de admin
    if not can_use_advanced_features(interaction.user, interaction.guild):
        await interaction.response.send_message("**🏷 | Apenas administradores podem ver as estatísticas.**", ephemeral=True)
        return
    
    # Define mês e ano
    now = datetime.now()
    target_mes = mes if mes else now.month
    target_ano = ano if ano else now.year
    
    # Validação
    if not (1 <= target_mes <= 12):
        await interaction.response.send_message("**🏷 | Mês deve estar entre 1 e 12.**", ephemeral=True)
        return
    
    if not (2020 <= target_ano <= 2030):
        await interaction.response.send_message("**🏷 | Ano deve estar entre 2020 e 2030.**", ephemeral=True)
        return
    
    try:
        conn = sqlite3.connect('tickets.db')
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT categoria, COUNT(*) as quantidade
            FROM tickets 
            WHERE strftime('%m', data_abertura) = ? AND strftime('%Y', data_abertura) = ?
            GROUP BY categoria
            ORDER BY quantidade DESC
        ''', (f"{target_mes:02d}", str(target_ano)))
        
        stats_categoria = cursor.fetchall()
        
        # Total geral do mês
        cursor.execute('''
            SELECT COUNT(*) as total
            FROM tickets 
            WHERE strftime('%m', data_abertura) = ? AND strftime('%Y', data_abertura) = ?
        ''', (f"{target_mes:02d}", str(target_ano)))
        
        total_mes = cursor.fetchone()[0]
        
        # Tickets fechados no mês
        cursor.execute('''
            SELECT COUNT(*) as fechados
            FROM tickets 
            WHERE strftime('%m', data_abertura) = ? AND strftime('%Y', data_abertura) = ?
            AND status = 'fechado'
        ''', (f"{target_mes:02d}", str(target_ano)))
        
        total_fechados = cursor.fetchone()[0]
        
        conn.close()
        
        # Cria o embed
        meses_nome = [
            "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
            "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"
        ]
        
        embed = discord.Embed(
            title="HDTZ - Haxball do Tio Zé | Estatísticas",
            description=f"<:3Estatsticas:1396678248808845465> ・`TICKETS DE {meses_nome[target_mes-1].upper()} DE {target_ano}`",
            color=discord.Color.from_rgb(255, 186, 0),
            timestamp=datetime.now()
        )
        
        if interaction.guild.icon:
            embed.set_author(name=interaction.guild.name, icon_url=interaction.guild.icon.url)
        
        embed.set_thumbnail(url="https://cdn.discordapp.com/attachments/1392962805472170207/1400983692938076160/Design_sem_nome_5.png")
        
        total_abertos = total_mes - total_fechados
        percentual_fechados = (total_fechados / total_mes * 100) if total_mes > 0 else 0
        
        embed.add_field(
            name="<:0Formlario:1396675331817083013> Resumo Geral",
            value=f"<:3Tick:1399108824488476782> **Total Criados:** `{total_mes}`\n" +
                  f"<:3Positivo:1396875464081018920> **Fechados:** `{total_fechados}` ({percentual_fechados:.1f}%)\n" +
                  f"<:3Cadeado:1396678201844957184> **Abertos:** `{total_abertos}`",
            inline=False
        )
        
        # Estatísticas por categoria
        if stats_categoria:
            # Emojis por categoria
            categoria_emojis = {
                "suporte": "🔧",
                "apelação": "⚖️", 
                "Denúncia": "🚨",
                "VIPs": "👑"
            }
            
            stats_texto = []
            for categoria, quantidade in stats_categoria:
                emoji = categoria_emojis.get(categoria, "🎫")
                percentual = (quantidade / total_mes * 100) if total_mes > 0 else 0
                
                # Barra de progresso visual
                barra_cheia = "█"
                barra_vazia = "░"
                tamanho_barra = 10
                preenchimento = int((percentual / 100) * tamanho_barra)
                barra = barra_cheia * preenchimento + barra_vazia * (tamanho_barra - preenchimento)
                
                stats_texto.append(
                    f"{emoji} **{categoria.title()}**\n" +
                    f"└ `{quantidade}` tickets ({percentual:.1f}%) `{barra}`"
                )
            
            embed.add_field(
                name="<:3Estatsticas:1396678248808845465> Distribuição por Categoria",
                value="\n\n".join(stats_texto),
                inline=False
            )
        else:
            embed.add_field(
                name="<:3Estatsticas:1396678248808845465> Distribuição por Categoria",
                value="**Nenhum ticket encontrado para este período.**",
                inline=False
            )
        
        # Adiciona informações extras no footer
        embed.set_footer(
            text=f"HDTZ - Estatísticas de {meses_nome[target_mes-1]} {target_ano}"
        )
        
        await interaction.response.send_message(embed=embed)
        
    except Exception as e:
        await interaction.response.send_message(f"**❌ | Erro ao buscar estatísticas: {e}**", ephemeral=True)
        print(f"Erro no comando statsticket: {e}")

# Comando para abrir o painel de staff com comando
@bot.tree.command(name="painelstaff", description="[🔧] Abre o painel de gerenciamento de tickets")
@app_commands.default_permissions(manage_channels=True)
async def painel_staff_comando(interaction: discord.Interaction):
    """Comando para abrir o painel de staff"""
    # Verifica se é um canal de ticket
    if not isinstance(interaction.channel, discord.TextChannel) or not interaction.channel.name.startswith("🎫・"):
        await interaction.response.send_message("**🏷 | Este comando só pode ser usado em canais de ticket.**", ephemeral=True)
        return
    
    # Verifica se é staff
    if not has_staff_permissions(interaction.user, interaction.guild):
        await interaction.response.send_message("**🏷 | Apenas a Staff tem permissão para usar este comando.**", ephemeral=True)
        return
    
    # Verifica se o staff assumiu o ticket
    channel_id = interaction.channel.id
    if interaction.user.id not in ticket_assumido_por.get(channel_id, []):
        await interaction.response.send_message("**🏷 | Você precisa assumir o ticket para usar o painel de staff.**", ephemeral=True)
        return

    # Identifica o tipo do ticket atual
    ticket_type = ticket_types.get(channel_id, "suporte")
    
    # Criar view personalizada baseada no tipo do ticket
    view = discord.ui.View(timeout=None)
    
    # Botões básicos
    add_staff_button = discord.ui.Button(
        style=discord.ButtonStyle.success,
        label="Adicionar Staff",
        emoji="<:3Mais:1396875479369252864>",
        custom_id=f"add_staff_{channel_id}"
    )
    
    remove_staff_button = discord.ui.Button(
        style=discord.ButtonStyle.danger,
        label="Remover Staff", 
        emoji="<:3Negativo:1396875481986502677>",
        custom_id=f"remove_staff_{channel_id}"
    )
    
    add_member_button = discord.ui.Button(
        style=discord.ButtonStyle.success,
        label="Adicionar Membro",
        emoji="<:3Mais:1396875479369252864>",
        custom_id=f"add_member_{channel_id}"
    )
    
    remove_member_button = discord.ui.Button(
        style=discord.ButtonStyle.danger,
        label="Remover Membro",
        emoji="<:3Negativo:1396875481986502677>",
        custom_id=f"remove_member_{channel_id}"
    )
    
    # Adiciona os botões básicos
    view.add_item(add_staff_button)
    view.add_item(remove_staff_button)
    view.add_item(add_member_button)
    view.add_item(remove_member_button)
    
    # Botões específicos por tipo de ticket
    if ticket_type == "VIPs":
        vip_button = discord.ui.Button(
            style=discord.ButtonStyle.primary,
            label="Verificar Pagamento",
            emoji="💳",
            custom_id=f"check_payment_{channel_id}"
        )
    
    elif ticket_type == "Denúncia":
        # Para tickets de denúncia
        evidence_button = discord.ui.Button(
            style=discord.ButtonStyle.primary,
            label="Solicitar Evidências",
            emoji="📋",
            custom_id=f"request_evidence_{channel_id}"
        )
    
    elif ticket_type == "apelação":
        history_button = discord.ui.Button(
            style=discord.ButtonStyle.primary,
            label="Verificar Histórico",
            emoji="📜",
            custom_id=f"check_history_{channel_id}"
        )
    
    # Botão de Fechar Agora
    if channel_id in tickets_finalizados:
        close_now_button = discord.ui.Button(
            style=discord.ButtonStyle.danger,
            label="Fechar Agora",
            emoji="<:3Negativo:1396875481986502677>",
            custom_id=f"close_now_{channel_id}"
        )
        
        # Callback para o botão de fechar agora
        async def close_now_staff_callback(btn_interaction):
            # Usa os dados do modal já salvos quando o ticket foi finalizado
            finalizacao_info = tickets_finalizados.get(channel_id, {})
            modal_data = finalizacao_info.get("modal_data")
            
            if not modal_data:
                await btn_interaction.response.send_message("**🏷 | Erro: Dados de finalização não encontrados.**", ephemeral=True)
                return
            
            # Cancela o fechamento automático
            tickets_finalizados.pop(channel_id, None)
            
            # Obtém o autor do ticket
            get_author = get_ticket_author(interaction.channel)
            author_id = await get_author()
            author = interaction.guild.get_member(author_id)

            await btn_interaction.response.send_message("**🏷 | Gerando a transcrição e fechando o ticket em 3 segundos... Por favor, aguarde!**", ephemeral=False)
            try:
                ticket_type = ticket_types.get(channel_id)
                
                if not ticket_type:
                    channel_name = interaction.channel.name
                    if "ap-" in channel_name:
                        ticket_type = "apelação"
                    elif "rep-" in channel_name:
                        ticket_type = "Denúncia"
                    else:
                        ticket_type = "suporte"
                
                transcript_channel_id = TRANSCRIPT_CHANNELS.get(ticket_type, TRANSCRIPT_CHANNEL_ID)
                transcript_channel = interaction.guild.get_channel(transcript_channel_id)
                
                if transcript_channel:
                    file = await gerar_transcript_html(interaction.channel)
                    embed = discord.Embed(
                        title=f"{TICKET_EMOJIS.get(ticket_type, '🎫')} Detalhes do Fechamento do Ticket ({ticket_type.capitalize() if ticket_type else 'Desconhecido'})",
                        color=discord.Color.from_rgb(255, 186, 0),
                        timestamp=datetime.now()
                    )
                    embed.add_field(name="Motivo por fechar", value=modal_data["motivo_fechar"], inline=False)
                    if "sala" in modal_data:
                        embed.add_field(name="Sala", value=modal_data["sala"], inline=False)
                    embed.set_footer(text="HDTZ - Sistema de Tickets")
    
                    await transcript_channel.send(
                        f"**📝 | Transcript do ticket `{interaction.channel.name}` fechado por {btn_interaction.user.mention}:**\n**TicketID:** `{author_id}`",
                        embed=embed,
                        file=file
                    )
                
            except Exception as e:
                print(f"Erro ao enviar transcript: {e}")
                
            fechar_ticket(channel_id, btn_interaction.user.id)
            
            parar_monitoramento_ticket(channel_id)
            
            await asyncio.sleep(3)
            await interaction.channel.delete()
            
            ticket_assumido_por.pop(channel_id, None)
            ticket_membros_adicionados.pop(channel_id, None)
            ticket_types.pop(channel_id, None)
        
        close_now_button.callback = close_now_staff_callback
        view.add_item(close_now_button)
    
    # Criar a embed do painel
    embed = discord.Embed(
        title="HDTZ - Haxball do Tio Zé | Painel Staff",
        description=f"👋 Olá {interaction.user.mention}, bem-vindo ao painel de staff.",
        color=discord.Color.from_rgb(255, 186, 0)
    )
    
    # Adiciona informações aos campos da embed
    embed.add_field(
        name="📌 Gerenciamento de Staff",
        value=(
            "**Adicionar Staff:** Permite incluir outro staff\n"
            "**Remover Staff:** Remove um staff adicionado ao ticket"
        ),
        inline=False
    )
    
    embed.add_field(
        name="👥 Gerenciamento de Membros",
        value=(
            "**Adicionar Membro:** Inclui outro membro no ticket\n"
            "**Remover Membro:** Remove um membro do ticket"
        ),
        inline=False
    )
    
    if channel_id in tickets_finalizados:
        finalizacao_info = tickets_finalizados[channel_id]
        tempo_fechamento = finalizacao_info["timestamp"] + timedelta(hours=12)
        embed.add_field(
            name="⚠️ Ticket Finalizado",
            value=(
                f"**Fechamento automático:** <t:{int(tempo_fechamento.timestamp())}:R>\n"
                f"**Fechar Agora:** Use o botão para fechar antes do prazo"
            ),
            inline=False
        )
    
    embed.set_footer(text="HDTZ - Sistema de Tickets")
    
    await interaction.response.send_message(
        embed=embed,
        view=view,
        ephemeral=True
    )


# Comando para visualizar ranking das avaliações
@bot.tree.command(name="avaliacoes", description="[🔧] Mostra o resultado de avaliações da staff")
@app_commands.default_permissions(administrator=True)
async def avaliacoes_ranking(interaction: discord.Interaction):
    """Comando para visualizar ranking das avaliações"""
    
    # Verifica se é adm
    if not has_admin_permissions(interaction.user, interaction.guild):
        await interaction.response.send_message("**🏷 | Apenas administradores podem ver as estatísticas de avaliações.**", ephemeral=True)
        return
    
    conn = sqlite3.connect('tickets.db')
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            SELECT s.staff_id, COUNT(*) as total_avaliacoes, AVG(s.nota) as media
            FROM avaliacoes s
            GROUP BY s.staff_id
            HAVING total_avaliacoes >= 3
            ORDER BY media DESC, total_avaliacoes DESC
            LIMIT 10
        ''', ())
        
        ranking_staff = cursor.fetchall()
        
        # Total de avaliações no sistema
        cursor.execute('SELECT COUNT(*) FROM avaliacoes')
        total_geral = cursor.fetchone()[0]
        
        if total_geral == 0:
            await interaction.response.send_message("**<:3Estatsticas:1396678248808845465> | Ainda não há avaliações no sistema.**")
            return
        
        embed = discord.Embed(
            title="<:3Estrela:1396678251086348338> Ranking de Avaliações - HDTZ",
            color=discord.Color.gold(),
            timestamp=datetime.now()
        )
        
        if ranking_staff:
            ranking_texto = []
            for i, (staff_id, total_av, media) in enumerate(ranking_staff, 1):
                membro = interaction.guild.get_member(int(staff_id))
                nome = membro.display_name if membro else f"Staff ID: {staff_id}"
                
                emoji_posicao = {1: "🥇", 2: "🥈", 3: "🥉"}.get(i, f"**{i}.**")
                
                porcentagem = min(media * 10, 100)
                
                ranking_texto.append(f"{emoji_posicao} **{nome}** - `{porcentagem:.2f}%` - `{total_av}` avaliações")
            
            embed.add_field(
                name="<:0Campeonato:1396675343317733406> Top Staffs por Avaliação",
                value="\n".join(ranking_texto),
                inline=False
            )
        else:
            embed.add_field(
                name="<:3Estrela:1396678251086348338> Ranking",
                value="Nenhum staff tem pelo menos 3 avaliações ainda.",
                inline=False
            )
        
        embed.add_field(
            name="<:3Tick:1399108824488476782> Resumo",
            value=f"**Total de Avaliações:** `{total_geral}`",
            inline=False
        )
        
        embed.set_footer(text="HDTZ - Sistema de Avaliações")
        
        await interaction.response.send_message(embed=embed)
        
    except Exception as e:
        await interaction.response.send_message(f"**❌ | Erro ao buscar ranking: {e}**")
        print(f"Erro no comando avaliacoes: {e}")
    finally:
        conn.close()

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    # Verifica se é canal de DM ou não tem nome
    if not hasattr(message.channel, 'name') or not isinstance(message.channel, discord.TextChannel):
        await bot.process_commands(message)
        return

    if not message.channel.name.startswith("🎫・"):
        await bot.process_commands(message)
        return

    guild = message.guild
    channel_id = message.channel.id

    # Sistema para usuários com IDs permitidos
    if message.author.id in ALLOWED_USER_IDS:
        print(f"[DEBUG] Usuário com ID permitido detectado: {message.author.display_name} (ID: {message.author.id})")
        
        if channel_id not in ticket_assumido_por:
            ticket_assumido_por[channel_id] = []
        
        if message.author.id not in ticket_assumido_por[channel_id]:
            ticket_assumido_por[channel_id].append(message.author.id)
            print(f"[AUTO-ASSUME] {message.author.display_name} (ID: {message.author.id}) auto-assumiu o ticket {channel_id}")
            
            # Registrar no banco de dados
            try:
                await assumir_ticket_seguro(str(channel_id), message.author.id)
                print(f"[AUTO-ASSUME] Sucesso ao registrar no banco para ticket {channel_id}")
            except Exception as e:
                print(f"[ERROR] Erro ao registrar auto-assume no banco: {e}")
            
            try:
                await message.channel.send(
                    f"**🏷 | {message.author.mention} entrou no atendimento.**",
                    delete_after=30
                )
                print(f"[AUTO-ASSUME] Mensagem de notificação enviada para {channel_id}")
            except Exception as e:
                print(f"[ERROR] Erro ao enviar mensagem de auto-assume: {e}")
        else:
            print(f"[DEBUG] Usuário {message.author.display_name} já tinha assumido o ticket {channel_id}")
        
        # Registrar interação
        registrar_interacao(channel_id, message.author.id, "mensagem", message.author.id)
        await bot.process_commands(message)
        return

    if has_admin_permissions(message.author, message.guild):
        await bot.process_commands(message)
        return

    guild = message.guild
    channel_id = message.channel.id

    author_id = None
    async for msg in message.channel.history(limit=20, oldest_first=True):
        if msg.embeds:
            embed = msg.embeds[0]
            if embed.title and "Atendimento" in embed.title:
                for field in embed.fields:
                    if "Usuário:" in field.value:
                        try:
                            author_id = int(field.value.split("<@")[1].split(">")[0].replace("!", ""))
                        except Exception:
                            pass
                break

    if not author_id:
        await bot.process_commands(message)
        return

    assumido_por_ids = ticket_assumido_por.get(channel_id, [])
    membros_adicionados_ids = ticket_membros_adicionados.get(channel_id, [])

    if assumido_por_ids:
        if message.author.id not in [author_id] + assumido_por_ids + membros_adicionados_ids + ALLOWED_USER_IDS:
            await message.delete()
        else:
            if message.author.id in assumido_por_ids or message.author.id in ALLOWED_USER_IDS:
                registrar_interacao(channel_id, message.author.id, "mensagem", message.author.id)
            await bot.process_commands(message)
        return

    if message.author.id in [author_id] + membros_adicionados_ids + ALLOWED_USER_IDS:
        if message.author.id in ALLOWED_USER_IDS and message.author.id != author_id:
            if channel_id not in ticket_assumido_por:
                ticket_assumido_por[channel_id] = []
            
            if message.author.id not in ticket_assumido_por[channel_id]:
                ticket_assumido_por[channel_id].append(message.author.id)
                print(f"[AUTO-ASSUME] {message.author.display_name} (ID: {message.author.id}) auto-assumiu o ticket não assumido {channel_id}")
                
                # Registrar no banco de dados
                try:
                    await assumir_ticket_seguro(str(channel_id), message.author.id)
                except Exception as e:
                    print(f"[ERROR] Erro ao registrar auto-assume no banco: {e}")
                
                # Registrar interação
                registrar_interacao(channel_id, message.author.id, "mensagem", message.author.id)
                
                
                try:
                    await message.channel.send(
                        f"🔧 **{message.author.mention}** assumiu o atendimento.",
                        delete_after=10
                    )
                except Exception as e:
                    print(f"[ERROR] Erro ao enviar mensagem de auto-assume: {e}")
        
        await bot.process_commands(message)
        return

    # Staff que não assumiu não pode enviar mensagem
    if has_staff_permissions(message.author, guild) and message.author.id not in ALLOWED_USER_IDS:
        await message.delete()
        return

    await message.delete()

@bot.event
async def on_ready():
    print(f"Bot conectado como {bot.user}")
    
    # Limpar dados do bot do banco de dados
    await limpar_dados_bot_do_banco()
    
    # Limpar bot da memória também
    await limpar_bot_da_memoria()
    
    main_guild = bot.get_guild(1392245348898050168)  # Id do Servidor
    if main_guild:
        print("Verificando categorias de tickets...")
        for ticket_type, category_id in CATEGORY_IDS.items():
            category = discord.utils.get(main_guild.categories, id=category_id)
            if category:
                print(f"✓ Categoria '{ticket_type}' encontrada: {category.name}")
            else:
                print(f"✗ ERRO: Categoria '{ticket_type}' (ID: {category_id}) NÃO encontrada!")
        
        print("\nVerificando canais de transcript...")
        for ticket_type, channel_id in TRANSCRIPT_CHANNELS.items():
            channel = main_guild.get_channel(channel_id)
            if channel:
                print(f"✓ Canal de transcript para '{ticket_type}' encontrado: {channel.name}")
            else:
                print(f"✗ ERRO: Canal de transcript para '{ticket_type}' (ID: {channel_id}) NÃO encontrada!")
    
    print("Registrando views persistentes...")
    bot.add_view(TicketSelectView())
    print("✓ Views básicas registradas")
    
    print("Recriando views para tickets ativos...")
    conexao = sqlite3.connect('tickets.db')
    cursor = conexao.cursor()
    
    try:
        # Buscar tickets ativos
        cursor.execute("SELECT ticket_id, user_id, categoria, data_abertura FROM tickets WHERE status = 'aberto'")
        tickets_ativos = cursor.fetchall()
        
        for ticket in tickets_ativos:
            channel_id, author_id, categoria, data_abertura = ticket
            try:
                # Verificar se o canal ainda existe
                channel = bot.get_channel(int(channel_id))
                if not channel:
                    # Canal não existe mais, marcar ticket como fechado
                    print(f"⚠️ Canal {channel_id} não existe mais, marcando ticket como fechado...")
                    cursor.execute("UPDATE tickets SET status = 'fechado', data_fechamento = CURRENT_TIMESTAMP WHERE ticket_id = ?", (channel_id,))
                    conexao.commit()
                    continue
                
                author = bot.get_user(int(author_id)) or await bot.fetch_user(int(author_id))
                if author:
                    # Recriar a view de controle para cada ticket
                    bot.add_view(TicketControlView(author, categoria, data_abertura, int(channel_id)))
                    print(f"✓ View de controle recriada para o ticket #{channel_id}")
                else:
                    print(f"⚠️ Usuário {author_id} não encontrado para o ticket {channel_id}")
            except Exception as err:
                print(f"✗ Erro ao processar ticket {channel_id}: {err}")
        
        # Limpeza adicional: remover entradas
        print("🧹 Limpando estados órfãos...")
        tickets_finalizados.clear()  # limpeza completa
        
    except Exception as e:
        print(f"✗ Erro ao recriar views de controle: {e}")
    finally:
        conexao.close()
    
    # Sincronizar comandos slash
    try:
        await bot.tree.sync()
        print("✓ Comandos slash sincronizados com sucesso!")
    except Exception as e:
        print(f"✗ Erro ao sincronizar comandos slash: {e}")
        
    print("\n✅ Todas as views foram registradas com sucesso!")

# ===================== COMANDO PREFIX PARA RESET DE AVALIAÇÕES =====================

@bot.command(name='resetavaliacoes', hidden=True)
async def reset_avaliacoes_command(ctx):
    """Comando para resetar todas as avaliações do sistema - APENAS ALLOWED_USER_IDS"""
    
    # Verificação de segurança DUPLA
    if ctx.author.id not in ALLOWED_USER_IDS:
        return

    try:
        # Conexão com o banco
        conn = sqlite3.connect('tickets.db')
        cursor = conn.cursor()
        
        # Contar quantas avaliações existem antes do reset
        cursor.execute('SELECT COUNT(*) FROM avaliacoes')
        total_avaliacoes = cursor.fetchone()[0]
        
        # Resetar todas as avaliações
        cursor.execute('DELETE FROM avaliacoes')
        conn.commit()
        
        # Confirmar que foi limpo
        cursor.execute('SELECT COUNT(*) FROM avaliacoes')
        remaining = cursor.fetchone()[0]
        
        conn.close()
        
        # Embed de confirmação
        embed = discord.Embed(
            title="🔄 Sistema de Avaliações Resetado",
            description=(
                f"**✅ Reset realizado com sucesso!**\n\n"
                f"📊 **Avaliações removidas:** {total_avaliacoes}\n"
                f"🗃️ **Avaliações restantes:** {remaining}\n"
                f"👤 **Executado por:** {ctx.author.mention}\n"
                f"📅 **Data/Hora:** <t:{int(datetime.now().timestamp())}:F>"
            ),
            color=discord.Color.red()
        )
        embed.set_footer(text="HDTZ - Reset de Avaliações | Comando Restrito")
        
        await ctx.send(embed=embed)
        
        print(f"[RESET AVALIACOES] Executado por {ctx.author} (ID: {ctx.author.id}) - {total_avaliacoes} avaliações removidas")
        
    except Exception as e:
        # Embed de erro
        error_embed = discord.Embed(
            title="❌ Erro no Reset",
            description=f"**Erro ao resetar avaliações:**\n```{str(e)}```",
            color=discord.Color.red()
        )
        await ctx.send(embed=error_embed)
        
        # Log do erro
        print(f"[ERRO RESET AVALIACOES] {ctx.author} (ID: {ctx.author.id}): {e}")

# ===================== FIM DO COMANDO DE RESET =====================

try:
    bot.run(TOKEN)
except Exception as e:
    print(f"Erro ao iniciar o bot: {e}")

