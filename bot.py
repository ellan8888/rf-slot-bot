import discord
from discord.ext import commands
from datetime import datetime, timedelta
import pytz
import json
import asyncio

RF_LIST_FILE = "rf_list.json"
MESSAGE_ID_FILE = "monitor_message.json"
CHANNEL_NAME = "📊┃rf-slot"
DATA_FILE = "rf_slots.json"

TZ = pytz.timezone("Asia/Jakarta")

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

lock = asyncio.Lock()

def load_rf_list():
    try:
        with open(RF_LIST_FILE, "r") as f:
            return set(json.load(f)["rf"])
    except:
        return set()

def save_rf_list(rf_set):
    with open(RF_LIST_FILE, "w") as f:
        json.dump({"rf": sorted(rf_set)}, f, indent=2)

def get_target_datetime(input_time, input_date=None):
    now = datetime.now(TZ)
    h, m = map(int, input_time.split(":"))

    # 🔹 KALAU USER ISI TANGGAL
    if input_date:
        try:
            date_obj = datetime.fromisoformat(input_date)
            target = TZ.localize(
                date_obj.replace(hour=h, minute=m, second=0)
            )
        except ValueError:
            raise ValueError("Format tanggal salah (YYYY-MM-DD)")
    else:
        # 🔹 DEFAULT BEHAVIOR (hari ini / besok)
        target = now.replace(hour=h, minute=m, second=0)
        if target <= now:
            target += timedelta(days=1)

    return target.date().isoformat(), target.strftime("%H:%M")

def load_data():
    try:
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    except:
        return {}

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

def load_message_id():
    try:
        with open(MESSAGE_ID_FILE, "r") as f:
            return json.load(f).get("message_id")
    except:
        return None

def save_message_id(message_id):
    with open(MESSAGE_ID_FILE, "w") as f:
        json.dump({"message_id": message_id}, f)

def get_target_date(input_time):
    now = datetime.now(TZ)
    h, m = map(int, input_time.split(":"))
    target = now.replace(hour=h, minute=m, second=0)

    if target <= now:
        target += timedelta(days=1)

    return target.date().isoformat(), target.strftime("%H:%M")

async def update_embed(channel):
    data = load_data()
    now = datetime.now(TZ)

    embed = discord.Embed(
        title="📊 MONITOR SLOT RF",
        description="Jam menunjukkan kapan slot akan kosong",
        color=0x3498db
    )

    embed.add_field(name="\u200b", value="", inline=False)

    # =========================
    # 📊 SUMMARY (NO 5)
    # =========================
    today_key = now.date().isoformat()
    today_slots = data.get(today_key, [])
    total_rf = sum(len(slots) for slots in data.values())

    if today_slots:
        nearest = None
        nearest_diff = 99999

        for s in today_slots:
            h, m = map(int, s["time"].split(":"))
            slot_time = now.replace(hour=h, minute=m, second=0)
            diff = (slot_time - now).total_seconds() / 60
            if diff >= 0 and diff < nearest_diff:
                nearest_diff = diff
                nearest = s

        summary = (
            f"**Total RF** : {total_rf}\n"
            f"**Slot Terdekat** : RF {nearest['rf']} ({nearest['time']})"
            if nearest else
            f"**Total RF** : {total_rf}"
        )

    else:
        summary = "Belum ada slot hari ini"

    embed.add_field(
        name="📊 RINGKASAN HARI INI",
        value=summary,
        inline=False
    )

    embed.add_field(name="\u200b", value="", inline=False)

    # =========================
    # 📅 PER HARI
    # =========================
    if not data:
        embed.add_field(name="Info", value="Belum ada slot terisi.", inline=False)
    else:
        for idx, (date, slots) in enumerate(sorted(data.items())):
            date_obj = TZ.localize(datetime.fromisoformat(date))
            hari = date_obj.strftime("%A").upper()
            tanggal = date_obj.strftime("%d %b")
            is_today = date_obj.date() == now.date()

            # 🔥 HEADER (NO 1)
            if is_today:
                header = f"🟢 TODAY — {hari} ({tanggal})"
            else:
                header = f"📅 {hari} ({tanggal})"

            divider = "━━━━━━━━━━━━━━━━━━━━"

            # URUTKAN JAM
            slots = sorted(slots, key=lambda s: s["time"])

            rows = []
            for s in slots:
                h, m = map(int, s["time"].split(":"))
                slot_time = date_obj.replace(hour=h, minute=m)
                diff = (slot_time - now).total_seconds() / 60

                if diff <= 30:
                    icon = "🔴"
                elif diff <= 60:
                    icon = "🟡"
                else:
                    icon = "🟢"

                # 🔥 SLOT CARD (NO 2)
                rows.append(
                    f"{icon} **RF {s['rf']}**\n"
                    f"└─ ⏰ {s['time']} WIB\n"
                    f"└─ 👤 {s.get('name', 'Unknown')}"
                )

            embed.add_field(
                name=f"{header}\n{divider}",
                value="\n\n".join(rows),
                inline=False
            )

            if idx < len(data) - 1:
                embed.add_field(name="\u200b", value="", inline=False)

    embed.set_footer(
        text=f"Last updated • {now.strftime('%d %b %Y %H:%M')} WIB"
    )

    message_id = load_message_id()

    try:
        if message_id:
            msg = await channel.fetch_message(message_id)
            await msg.edit(embed=embed, view=SlotView())
        else:
            msg = await channel.send(embed=embed, view=SlotView())
            save_message_id(msg.id)
    except discord.NotFound:
        msg = await channel.send(embed=embed, view=SlotView())
        save_message_id(msg.id)

class SlotView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Isi Slot", style=discord.ButtonStyle.primary)
    async def isi(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(SlotModal())

    @discord.ui.button(label="Hapus Slot", style=discord.ButtonStyle.primary)
    async def hapus(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(DeleteSlotModal())

    @discord.ui.button(label="Manage RF", style=discord.ButtonStyle.primary)
    async def manage_rf(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ManageRFModal())

    @discord.ui.button(label="Check Status", style=discord.ButtonStyle.primary)
    async def status(self, interaction: discord.Interaction, button: discord.ui.Button):
        data = load_data()

        used_rf = set()
        for slots in data.values():
            for s in slots:
                used_rf.add(s["rf"])

        all_rf = load_rf_list()

        total_rf = len(all_rf)
        used_count = len(used_rf)
        empty_count = max(total_rf - used_count, 0)

        now = datetime.now(TZ).strftime("%H:%M")

        text = (
            "📊 **STATUS SLOT**\n\n"
            f"🔄 **Lagi Digunakan** : {used_count}\n"
            f"📭 **Slot Kosong**   : {empty_count}\n\n"
            f"Today at {now}"
        )

        await interaction.response.send_message(
            text,
            ephemeral=True
        )

    @discord.ui.button(label="Refresh", style=discord.ButtonStyle.primary)
    async def refresh(self, interaction: discord.Interaction, button: discord.ui.Button):
        await update_embed(interaction.channel)
        await interaction.response.send_message("♻️ Di-refresh", ephemeral=True)

class SlotModal(discord.ui.Modal, title="Isi Slot RF"):
    rf = discord.ui.TextInput(label="Nomor RF", placeholder="31")
    jam = discord.ui.TextInput(label="Jam Selesai (HH:MM)", placeholder="23:00")
    tanggal = discord.ui.TextInput(
        label="Tanggal (opsional)",
        placeholder="YYYY-MM-DD (contoh: 2026-01-10)",
        required=False
    )
    name = discord.ui.TextInput(label="Nama Pemakai RF", placeholder="Lan")

    async def on_submit(self, interaction: discord.Interaction):
        # ✅ RESPON CEPAT DULU (BIAR GA EXPIRED)
        await interaction.response.defer(ephemeral=True)

        async with lock:
            try:
                date, time = get_target_datetime(
                    self.jam.value,
                    self.tanggal.value.strip() or None
                )
            except ValueError as e:
                await interaction.followup.send(f"❌ {e}", ephemeral=True)
                return

            rf_number = int(self.rf.value)
            data = load_data()

            # 🔥 HAPUS RF DARI SEMUA TANGGAL
            for d in list(data.keys()):
                data[d] = [s for s in data[d] if s["rf"] != rf_number]
                if not data[d]:
                    del data[d]

            # ➕ TAMBAH SLOT BARU
            data.setdefault(date, []).append({
                "rf": rf_number,
                "time": time,
                "name": self.name.value
            })

            save_data(data)

        # 🔄 UPDATE EMBED (AMAN, INTERACTION SUDAH DI-DEFER)
        await update_embed(interaction.channel)

        # 📩 BALAS KE USER
        await interaction.followup.send(
            f"✅ RF {rf_number} berhasil disimpan",
            ephemeral=True
        )

class DeleteSlotModal(discord.ui.Modal, title="Hapus Slot RF"):
    rf = discord.ui.TextInput(
        label="Nomor RF yang ingin dihapus",
        placeholder="31"
    )

    async def on_submit(self, interaction: discord.Interaction):
        rf_number = int(self.rf.value)

        async with lock:
            data = load_data()
            found = False

            for date in list(data.keys()):
                slots = data[date]
                new_slots = [s for s in slots if s["rf"] != rf_number]

                if len(new_slots) != len(slots):
                    found = True
                    if new_slots:
                        data[date] = new_slots
                    else:
                        del data[date]  # hapus hari kalau kosong

            if found:
                save_data(data)

        if found:
            await update_embed(interaction.channel)
            await interaction.response.send_message(
                f"🗑️ RF {rf_number} berhasil dihapus",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                f"⚠️ RF {rf_number} tidak ditemukan",
                ephemeral=True
            )

class ManageRFModal(discord.ui.Modal, title="Manajemen RF"):
    rf = discord.ui.TextInput(
        label="Nomor RF",
        placeholder="32"
    )
    action = discord.ui.TextInput(
        label="Aksi (add / remove)",
        placeholder="add atau remove"
    )

    async def on_submit(self, interaction: discord.Interaction):
        rf_number = int(self.rf.value)
        action = self.action.value.lower().strip()

        rf_list = load_rf_list()
        data = load_data()

        used_rf = {s["rf"] for slots in data.values() for s in slots}

        # ➕ ADD RF
        if action == "add":
            if rf_number in rf_list:
                await interaction.response.send_message(
                    f"⚠️ RF {rf_number} sudah ada",
                    ephemeral=True
                )
                return

            rf_list.add(rf_number)
            save_rf_list(rf_list)

            await interaction.response.send_message(
                f"✅ RF {rf_number} berhasil ditambahkan",
                ephemeral=True
            )

        # 🗑️ REMOVE RF
        elif action == "remove":
            if rf_number not in rf_list:
                await interaction.response.send_message(
                    f"⚠️ RF {rf_number} tidak ditemukan",
                    ephemeral=True
                )
                return

            if rf_number in used_rf:
                await interaction.response.send_message(
                    f"❌ RF {rf_number} masih digunakan",
                    ephemeral=True
                )
                return

            rf_list.remove(rf_number)
            save_rf_list(rf_list)

            await interaction.response.send_message(
                f"🗑️ RF {rf_number} berhasil dihapus",
                ephemeral=True
            )

        else:
            await interaction.response.send_message(
                "❌ Aksi tidak valid (pakai add / remove)",
                ephemeral=True
            )

@bot.event
async def on_ready():
    print(f"Bot ku online {bot.user}")
    channel = discord.utils.get(bot.get_all_channels(), name=CHANNEL_NAME)
    if channel:
        await update_embed(channel)

import os
bot.run(os.getenv("DISCORD_TOKEN"))
