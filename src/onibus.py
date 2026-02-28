"""
Módulo de horários de ônibus - Americana/SP
Trajetos entre Casa (Jd. da Balsa), Trabalho (Vila Sta. Catarina) e Faculdade (Jd. Luciene)
"""

import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import BadRequest
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

import db

TZ = ZoneInfo("America/Sao_Paulo")

HORARIOS = {
    "casa_trabalho": {
        "nome": "🏠→💼 Casa → Trabalho",
        "horarios": [
            {"hora": "04:10", "linha": "220", "chegada": "04:38", "embarque": "R. Cira de O. Petrin, 622", "desembarque": "R. Vieira Bueno, 266"},
            {"hora": "04:40", "linha": "213", "chegada": "05:19", "embarque": "R. Rio das Velhas, 326", "desembarque": "R. Pe. Epifânio Estevan, 534"},
            {"hora": "05:10", "linha": "220", "chegada": "05:38", "embarque": "R. Cira de O. Petrin, 622", "desembarque": "R. Vieira Bueno, 266"},
            {"hora": "05:30", "linha": "213", "chegada": "06:09", "embarque": "R. Rio das Velhas, 326", "desembarque": "R. Pe. Epifânio Estevan, 534"},
            {"hora": "05:50", "linha": "220", "chegada": "06:18", "embarque": "R. Cira de O. Petrin, 622", "desembarque": "R. Vieira Bueno, 266"},
            {"hora": "06:30", "linha": "213", "chegada": "07:09", "embarque": "R. Rio das Velhas, 326", "desembarque": "R. Pe. Epifânio Estevan, 534"},
            {"hora": "06:30", "linha": "220", "chegada": "06:58", "embarque": "R. Cira de O. Petrin, 622", "desembarque": "R. Vieira Bueno, 266"},
            {"hora": "06:40", "linha": "213", "chegada": "07:19", "embarque": "R. Rio das Velhas, 326", "desembarque": "R. Pe. Epifânio Estevan, 534"},
            {"hora": "07:00", "linha": "220", "chegada": "07:28", "embarque": "R. Cira de O. Petrin, 622", "desembarque": "R. Vieira Bueno, 266"},
            {"hora": "07:20", "linha": "220", "chegada": "07:48", "embarque": "R. Cira de O. Petrin, 622", "desembarque": "R. Vieira Bueno, 266"},
            {"hora": "07:40", "linha": "213", "chegada": "08:19", "embarque": "R. Rio das Velhas, 326", "desembarque": "R. Pe. Epifânio Estevan, 534"},
            {"hora": "08:00", "linha": "220", "chegada": "08:28", "embarque": "R. Cira de O. Petrin, 622", "desembarque": "R. Vieira Bueno, 266"},
            {"hora": "08:40", "linha": "220", "chegada": "09:08", "embarque": "R. Cira de O. Petrin, 622", "desembarque": "R. Vieira Bueno, 266"},
            {"hora": "08:50", "linha": "213", "chegada": "09:29", "embarque": "R. Rio das Velhas, 326", "desembarque": "R. Pe. Epifânio Estevan, 534"},
            {"hora": "09:10", "linha": "220", "chegada": "09:38", "embarque": "R. Cira de O. Petrin, 622", "desembarque": "R. Vieira Bueno, 266"},
            {"hora": "10:10", "linha": "213", "chegada": "10:49", "embarque": "R. Rio das Velhas, 326", "desembarque": "R. Pe. Epifânio Estevan, 534"},
            {"hora": "10:10", "linha": "220", "chegada": "10:38", "embarque": "R. Cira de O. Petrin, 622", "desembarque": "R. Vieira Bueno, 266"},
            {"hora": "10:30", "linha": "220", "chegada": "10:58", "embarque": "R. Cira de O. Petrin, 622", "desembarque": "R. Vieira Bueno, 266"},
            {"hora": "11:00", "linha": "213", "chegada": "11:39", "embarque": "R. Rio das Velhas, 326", "desembarque": "R. Pe. Epifânio Estevan, 534"},
            {"hora": "11:00", "linha": "220", "chegada": "11:28", "embarque": "R. Cira de O. Petrin, 622", "desembarque": "R. Vieira Bueno, 266"},
            {"hora": "11:30", "linha": "220", "chegada": "11:58", "embarque": "R. Cira de O. Petrin, 622", "desembarque": "R. Vieira Bueno, 266"},
            {"hora": "11:50", "linha": "213", "chegada": "12:29", "embarque": "R. Rio das Velhas, 326", "desembarque": "R. Pe. Epifânio Estevan, 534"},
            {"hora": "12:10", "linha": "220", "chegada": "12:38", "embarque": "R. Cira de O. Petrin, 622", "desembarque": "R. Vieira Bueno, 266"},
            {"hora": "12:30", "linha": "213", "chegada": "13:09", "embarque": "R. Rio das Velhas, 326", "desembarque": "R. Pe. Epifânio Estevan, 534"},
            {"hora": "12:40", "linha": "220", "chegada": "13:08", "embarque": "R. Cira de O. Petrin, 622", "desembarque": "R. Vieira Bueno, 266"},
            {"hora": "13:10", "linha": "220", "chegada": "13:38", "embarque": "R. Cira de O. Petrin, 622", "desembarque": "R. Vieira Bueno, 266"},
            {"hora": "13:20", "linha": "213", "chegada": "13:59", "embarque": "R. Rio das Velhas, 326", "desembarque": "R. Pe. Epifânio Estevan, 534"},
            {"hora": "13:30", "linha": "220", "chegada": "13:58", "embarque": "R. Cira de O. Petrin, 622", "desembarque": "R. Vieira Bueno, 266"},
            {"hora": "14:00", "linha": "213", "chegada": "14:39", "embarque": "R. Rio das Velhas, 326", "desembarque": "R. Pe. Epifânio Estevan, 534"},
            {"hora": "14:00", "linha": "220", "chegada": "14:28", "embarque": "R. Cira de O. Petrin, 622", "desembarque": "R. Vieira Bueno, 266"},
            {"hora": "14:50", "linha": "213", "chegada": "15:29", "embarque": "R. Rio das Velhas, 326", "desembarque": "R. Pe. Epifânio Estevan, 534"},
            {"hora": "15:10", "linha": "220", "chegada": "15:38", "embarque": "R. Cira de O. Petrin, 622", "desembarque": "R. Vieira Bueno, 266"},
            {"hora": "15:50", "linha": "220", "chegada": "16:18", "embarque": "R. Cira de O. Petrin, 622", "desembarque": "R. Vieira Bueno, 266"},
            {"hora": "16:10", "linha": "213", "chegada": "16:49", "embarque": "R. Rio das Velhas, 326", "desembarque": "R. Pe. Epifânio Estevan, 534"},
            {"hora": "16:20", "linha": "220", "chegada": "16:48", "embarque": "R. Cira de O. Petrin, 622", "desembarque": "R. Vieira Bueno, 266"},
            {"hora": "16:40", "linha": "220", "chegada": "17:08", "embarque": "R. Cira de O. Petrin, 622", "desembarque": "R. Vieira Bueno, 266"},
            {"hora": "16:50", "linha": "213", "chegada": "17:29", "embarque": "R. Rio das Velhas, 326", "desembarque": "R. Pe. Epifânio Estevan, 534"},
            {"hora": "17:10", "linha": "213", "chegada": "17:49", "embarque": "R. Rio das Velhas, 326", "desembarque": "R. Pe. Epifânio Estevan, 534"},
            {"hora": "17:20", "linha": "220", "chegada": "17:48", "embarque": "R. Cira de O. Petrin, 622", "desembarque": "R. Vieira Bueno, 266"},
            {"hora": "18:10", "linha": "220", "chegada": "18:38", "embarque": "R. Cira de O. Petrin, 622", "desembarque": "R. Vieira Bueno, 266"},
            {"hora": "18:20", "linha": "213", "chegada": "18:59", "embarque": "R. Rio das Velhas, 326", "desembarque": "R. Pe. Epifânio Estevan, 534"},
            {"hora": "19:20", "linha": "220", "chegada": "19:48", "embarque": "R. Cira de O. Petrin, 622", "desembarque": "R. Vieira Bueno, 266"},
            {"hora": "20:30", "linha": "220", "chegada": "20:58", "embarque": "R. Cira de O. Petrin, 622", "desembarque": "R. Vieira Bueno, 266"},
            {"hora": "20:40", "linha": "213", "chegada": "21:19", "embarque": "R. Rio das Velhas, 326", "desembarque": "R. Pe. Epifânio Estevan, 534"},
            {"hora": "21:40", "linha": "220", "chegada": "22:08", "embarque": "R. Cira de O. Petrin, 622", "desembarque": "R. Vieira Bueno, 266"},
            {"hora": "21:50", "linha": "213", "chegada": "22:29", "embarque": "R. Rio das Velhas, 326", "desembarque": "R. Pe. Epifânio Estevan, 534"},
            {"hora": "22:50", "linha": "220", "chegada": "23:18", "embarque": "R. Cira de O. Petrin, 622", "desembarque": "R. Vieira Bueno, 266"},
        ],
    },
    "trabalho_faculdade": {
        "nome": "💼→🎓 Trabalho → Faculdade",
        "horarios": [
            # ── Manhã ────────────────────────────────────────────────────
            {"hora": "05:19", "linha": "114", "chegada": "05:32", "embarque": "Av. de Cillo, 269", "desembarque": "R. Álvaro Cechino, 69"},
            {"hora": "05:41", "linha": "103", "chegada": "05:55", "embarque": "R. Duque de Caxias, 575", "desembarque": "R. Álvaro Cechino, 69"},
            {"hora": "05:56", "linha": "225", "chegada": "06:22", "embarque": "Av. de Cillo, 269", "desembarque": "R. Eugênio Bertine, 90 ⭐"},
            {"hora": "06:12", "linha": "102", "chegada": "06:26", "embarque": "Av. de Cillo, 269", "desembarque": "R. Álvaro Cechino, 69"},
            {"hora": "06:19", "linha": "114", "chegada": "06:32", "embarque": "Av. de Cillo, 269", "desembarque": "R. Álvaro Cechino, 69"},
            {"hora": "07:16", "linha": "225", "chegada": "07:42", "embarque": "Av. de Cillo, 269", "desembarque": "R. Eugênio Bertine, 90 ⭐"},
            {"hora": "07:19", "linha": "114", "chegada": "07:32", "embarque": "Av. de Cillo, 269", "desembarque": "R. Álvaro Cechino, 69"},
            {"hora": "07:34", "linha": "114", "chegada": "07:47", "embarque": "Av. de Cillo, 269", "desembarque": "R. Álvaro Cechino, 69"},
            {"hora": "07:41", "linha": "103", "chegada": "07:55", "embarque": "R. Duque de Caxias, 575", "desembarque": "R. Álvaro Cechino, 69"},
            {"hora": "07:49", "linha": "114", "chegada": "08:02", "embarque": "Av. de Cillo, 269", "desembarque": "R. Álvaro Cechino, 69"},
            {"hora": "08:22", "linha": "102", "chegada": "08:36", "embarque": "Av. de Cillo, 269", "desembarque": "R. Álvaro Cechino, 69"},
            {"hora": "08:29", "linha": "114", "chegada": "08:42", "embarque": "Av. de Cillo, 269", "desembarque": "R. Álvaro Cechino, 69"},
            {"hora": "08:31", "linha": "225", "chegada": "08:57", "embarque": "Av. de Cillo, 269", "desembarque": "R. Eugênio Bertine, 90 ⭐"},
            # ── Meio-dia ─────────────────────────────────────────────────
            {"hora": "09:39", "linha": "114", "chegada": "09:52", "embarque": "Av. de Cillo, 269", "desembarque": "R. Álvaro Cechino, 69"},
            {"hora": "09:51", "linha": "225", "chegada": "10:17", "embarque": "Av. de Cillo, 269", "desembarque": "R. Eugênio Bertine, 90 ⭐"},
            {"hora": "10:01", "linha": "103", "chegada": "10:15", "embarque": "R. Duque de Caxias, 575", "desembarque": "R. Álvaro Cechino, 69"},
            {"hora": "10:19", "linha": "114", "chegada": "10:32", "embarque": "Av. de Cillo, 269", "desembarque": "R. Álvaro Cechino, 69"},
            {"hora": "11:19", "linha": "114", "chegada": "11:32", "embarque": "Av. de Cillo, 269", "desembarque": "R. Álvaro Cechino, 69"},
            {"hora": "11:22", "linha": "102", "chegada": "11:36", "embarque": "Av. de Cillo, 269", "desembarque": "R. Álvaro Cechino, 69"},
            {"hora": "11:41", "linha": "225", "chegada": "12:07", "embarque": "Av. de Cillo, 269", "desembarque": "R. Eugênio Bertine, 90 ⭐"},
            {"hora": "12:01", "linha": "103", "chegada": "12:15", "embarque": "R. Duque de Caxias, 575", "desembarque": "R. Álvaro Cechino, 69"},
            {"hora": "12:14", "linha": "114", "chegada": "12:27", "embarque": "Av. de Cillo, 269", "desembarque": "R. Álvaro Cechino, 69"},
            # ── Tarde ────────────────────────────────────────────────────
            {"hora": "13:01", "linha": "225", "chegada": "13:27", "embarque": "Av. de Cillo, 269", "desembarque": "R. Eugênio Bertine, 90 ⭐"},
            {"hora": "13:22", "linha": "102", "chegada": "13:36", "embarque": "Av. de Cillo, 269", "desembarque": "R. Álvaro Cechino, 69"},
            {"hora": "13:39", "linha": "114", "chegada": "13:52", "embarque": "Av. de Cillo, 269", "desembarque": "R. Álvaro Cechino, 69"},
            {"hora": "14:01", "linha": "103", "chegada": "14:15", "embarque": "R. Duque de Caxias, 575", "desembarque": "R. Álvaro Cechino, 69"},
            {"hora": "14:21", "linha": "225", "chegada": "14:47", "embarque": "Av. de Cillo, 269", "desembarque": "R. Eugênio Bertine, 90 ⭐"},
            {"hora": "14:24", "linha": "114", "chegada": "14:37", "embarque": "Av. de Cillo, 269", "desembarque": "R. Álvaro Cechino, 69"},
            {"hora": "15:22", "linha": "102", "chegada": "15:36", "embarque": "Av. de Cillo, 269", "desembarque": "R. Álvaro Cechino, 69"},
            {"hora": "15:39", "linha": "114", "chegada": "15:52", "embarque": "Av. de Cillo, 269", "desembarque": "R. Álvaro Cechino, 69"},
            {"hora": "15:41", "linha": "225", "chegada": "16:07", "embarque": "Av. de Cillo, 269", "desembarque": "R. Eugênio Bertine, 90 ⭐"},
            {"hora": "16:09", "linha": "114", "chegada": "16:22", "embarque": "Av. de Cillo, 269", "desembarque": "R. Álvaro Cechino, 69"},
            {"hora": "16:29", "linha": "114", "chegada": "16:42", "embarque": "Av. de Cillo, 269", "desembarque": "R. Álvaro Cechino, 69"},
            {"hora": "17:01", "linha": "103", "chegada": "17:15", "embarque": "R. Duque de Caxias, 575", "desembarque": "R. Álvaro Cechino, 69"},
            {"hora": "17:01", "linha": "225", "chegada": "17:27", "embarque": "Av. de Cillo, 269", "desembarque": "R. Eugênio Bertine, 90 ⭐"},
            {"hora": "17:09", "linha": "114", "chegada": "17:22", "embarque": "Av. de Cillo, 269", "desembarque": "R. Álvaro Cechino, 69"},
            {"hora": "17:22", "linha": "102", "chegada": "17:36", "embarque": "Av. de Cillo, 269", "desembarque": "R. Álvaro Cechino, 69"},
            {"hora": "17:49", "linha": "114", "chegada": "18:02", "embarque": "Av. de Cillo, 269", "desembarque": "R. Álvaro Cechino, 69"},
            # ── Noite (horário de pico p/ faculdade) ─────────────────────
            {"hora": "18:07", "linha": "102", "chegada": "18:21", "embarque": "Av. de Cillo, 269", "desembarque": "R. Álvaro Cechino, 69"},
            {"hora": "18:08", "linha": "114", "chegada": "18:22", "embarque": "Av. de Cillo, 269", "desembarque": "R. Álvaro Cechino, 69"},
            {"hora": "18:11", "linha": "200", "chegada": "18:33", "embarque": "R. Pe. Epifânio Estevan, 534", "desembarque": "R. Álvaro Cechino, 69"},
            {"hora": "18:21", "linha": "225", "chegada": "18:47", "embarque": "Av. de Cillo, 269", "desembarque": "R. Eugênio Bertine, 90 ⭐"},
            {"hora": "18:23", "linha": "114", "chegada": "18:37", "embarque": "Av. de Cillo, 269", "desembarque": "R. Álvaro Cechino, 69"},
            {"hora": "18:51", "linha": "103", "chegada": "19:05", "embarque": "R. Duque de Caxias, 575", "desembarque": "R. Álvaro Cechino, 69"},
            {"hora": "18:56", "linha": "205", "chegada": "19:12", "embarque": "R. Pe. Epifânio Estevan, 534", "desembarque": "R. Álvaro Cechino, 69"},
            {"hora": "18:59", "linha": "105", "chegada": "19:11", "embarque": "R. Ari Meireles, 473", "desembarque": "R. Joaquim Leitão, 5a"},
            {"hora": "19:22", "linha": "102", "chegada": "19:36", "embarque": "Av. de Cillo, 269", "desembarque": "R. Álvaro Cechino, 69"},
            {"hora": "19:41", "linha": "225", "chegada": "20:07", "embarque": "Av. de Cillo, 269", "desembarque": "R. Eugênio Bertine, 90 ⭐"},
            {"hora": "20:02", "linha": "118", "chegada": "20:27", "embarque": "Av. de Cillo, 269", "desembarque": "R. Álvaro Cechino, 69"},
            {"hora": "20:07", "linha": "102", "chegada": "20:21", "embarque": "Av. de Cillo, 269", "desembarque": "R. Álvaro Cechino, 69"},
            {"hora": "20:18", "linha": "114", "chegada": "20:32", "embarque": "Av. de Cillo, 269", "desembarque": "R. Álvaro Cechino, 69"},
            {"hora": "20:46", "linha": "205", "chegada": "21:02", "embarque": "R. Pe. Epifânio Estevan, 534", "desembarque": "R. Álvaro Cechino, 69"},
            {"hora": "20:49", "linha": "105", "chegada": "21:01", "embarque": "R. Ari Meireles, 473", "desembarque": "R. Joaquim Leitão, 5a"},
            {"hora": "21:01", "linha": "225", "chegada": "21:27", "embarque": "Av. de Cillo, 269", "desembarque": "R. Eugênio Bertine, 90 ⭐"},
            {"hora": "21:18", "linha": "114", "chegada": "21:32", "embarque": "Av. de Cillo, 269", "desembarque": "R. Álvaro Cechino, 69"},
            {"hora": "21:26", "linha": "200", "chegada": "21:48", "embarque": "R. Pe. Epifânio Estevan, 534", "desembarque": "R. Álvaro Cechino, 69"},
            {"hora": "21:39", "linha": "105", "chegada": "21:51", "embarque": "R. Ari Meireles, 473", "desembarque": "R. Joaquim Leitão, 5a"},
            {"hora": "21:42", "linha": "102", "chegada": "21:56", "embarque": "Av. de Cillo, 269", "desembarque": "R. Álvaro Cechino, 69"},
            {"hora": "22:27", "linha": "102", "chegada": "22:41", "embarque": "Av. de Cillo, 269", "desembarque": "R. Álvaro Cechino, 69"},
            {"hora": "22:28", "linha": "114", "chegada": "22:42", "embarque": "Av. de Cillo, 269", "desembarque": "R. Álvaro Cechino, 69"},
            {"hora": "22:36", "linha": "205", "chegada": "22:52", "embarque": "R. Pe. Epifânio Estevan, 534", "desembarque": "R. Álvaro Cechino, 69"},
            {"hora": "22:41", "linha": "225", "chegada": "23:07", "embarque": "Av. de Cillo, 269", "desembarque": "R. Eugênio Bertine, 90 ⭐"},
            {"hora": "23:22", "linha": "102", "chegada": "23:36", "embarque": "Av. de Cillo, 269", "desembarque": "R. Álvaro Cechino, 69"},
            {"hora": "23:29", "linha": "105", "chegada": "23:41", "embarque": "R. Ari Meireles, 473", "desembarque": "R. Joaquim Leitão, 5a"},
        ],
    },
    "faculdade_casa": {
        "nome": "🎓→🏠 Faculdade → Casa",
        "horarios": [
            # ── Manhã ────────────────────────────────────────────────────
            {"hora": "04:37", "linha": "220", "chegada": "05:26", "embarque": "R. São Gabriel, 1783", "desembarque": "Av. Luiz Bassete"},
            {"hora": "05:17", "linha": "220", "chegada": "06:06", "embarque": "R. São Gabriel, 1783", "desembarque": "Av. Luiz Bassete"},
            {"hora": "05:45", "linha": "213", "chegada": "06:40", "embarque": "R. Paraná, 1605", "desembarque": "Av. Luiz Bassete"},
            {"hora": "05:57", "linha": "220", "chegada": "06:46", "embarque": "R. São Gabriel, 1783", "desembarque": "Av. Luiz Bassete"},
            {"hora": "06:17", "linha": "220", "chegada": "07:06", "embarque": "R. São Gabriel, 1783", "desembarque": "Av. Luiz Bassete"},
            {"hora": "06:37", "linha": "220", "chegada": "07:26", "embarque": "R. São Gabriel, 1783", "desembarque": "Av. Luiz Bassete"},
            {"hora": "06:45", "linha": "213", "chegada": "07:40", "embarque": "R. Paraná, 1605", "desembarque": "Av. Luiz Bassete"},
            {"hora": "07:07", "linha": "220", "chegada": "07:56", "embarque": "R. São Gabriel, 1783", "desembarque": "Av. Luiz Bassete"},
            {"hora": "07:27", "linha": "220", "chegada": "08:16", "embarque": "R. São Gabriel, 1783", "desembarque": "Av. Luiz Bassete"},
            {"hora": "07:35", "linha": "213", "chegada": "08:30", "embarque": "R. Paraná, 1605", "desembarque": "Av. Luiz Bassete"},
            {"hora": "07:55", "linha": "213", "chegada": "08:50", "embarque": "R. Paraná, 1605", "desembarque": "Av. Luiz Bassete"},
            {"hora": "08:17", "linha": "220", "chegada": "09:06", "embarque": "R. São Gabriel, 1783", "desembarque": "Av. Luiz Bassete"},
            {"hora": "08:47", "linha": "220", "chegada": "09:36", "embarque": "R. São Gabriel, 1783", "desembarque": "Av. Luiz Bassete"},
            {"hora": "08:55", "linha": "213", "chegada": "09:50", "embarque": "R. Paraná, 1605", "desembarque": "Av. Luiz Bassete"},
            # ── Meio-dia ─────────────────────────────────────────────────
            {"hora": "09:27", "linha": "220", "chegada": "10:16", "embarque": "R. São Gabriel, 1783", "desembarque": "Av. Luiz Bassete"},
            {"hora": "09:47", "linha": "220", "chegada": "10:36", "embarque": "R. São Gabriel, 1783", "desembarque": "Av. Luiz Bassete"},
            {"hora": "09:55", "linha": "213", "chegada": "10:50", "embarque": "R. Paraná, 1605", "desembarque": "Av. Luiz Bassete"},
            {"hora": "10:27", "linha": "220", "chegada": "11:16", "embarque": "R. São Gabriel, 1783", "desembarque": "Av. Luiz Bassete"},
            {"hora": "11:25", "linha": "213", "chegada": "12:20", "embarque": "R. Paraná, 1605", "desembarque": "Av. Luiz Bassete"},
            {"hora": "11:27", "linha": "220", "chegada": "12:16", "embarque": "R. São Gabriel, 1783", "desembarque": "Av. Luiz Bassete"},
            {"hora": "11:57", "linha": "220", "chegada": "12:46", "embarque": "R. São Gabriel, 1783", "desembarque": "Av. Luiz Bassete"},
            {"hora": "12:15", "linha": "213", "chegada": "13:10", "embarque": "R. Paraná, 1605", "desembarque": "Av. Luiz Bassete"},
            {"hora": "12:17", "linha": "220", "chegada": "13:06", "embarque": "R. São Gabriel, 1783", "desembarque": "Av. Luiz Bassete"},
            {"hora": "12:47", "linha": "220", "chegada": "13:36", "embarque": "R. São Gabriel, 1783", "desembarque": "Av. Luiz Bassete"},
            {"hora": "12:55", "linha": "213", "chegada": "13:50", "embarque": "R. Paraná, 1605", "desembarque": "Av. Luiz Bassete"},
            # ── Tarde ────────────────────────────────────────────────────
            {"hora": "13:17", "linha": "220", "chegada": "14:06", "embarque": "R. São Gabriel, 1783", "desembarque": "Av. Luiz Bassete"},
            {"hora": "13:45", "linha": "213", "chegada": "14:40", "embarque": "R. Paraná, 1605", "desembarque": "Av. Luiz Bassete"},
            {"hora": "14:27", "linha": "220", "chegada": "15:16", "embarque": "R. São Gabriel, 1783", "desembarque": "Av. Luiz Bassete"},
            {"hora": "14:35", "linha": "213", "chegada": "15:30", "embarque": "R. Paraná, 1605", "desembarque": "Av. Luiz Bassete"},
            {"hora": "14:57", "linha": "220", "chegada": "15:46", "embarque": "R. São Gabriel, 1783", "desembarque": "Av. Luiz Bassete"},
            {"hora": "15:15", "linha": "213", "chegada": "16:10", "embarque": "R. Paraná, 1605", "desembarque": "Av. Luiz Bassete"},
            {"hora": "15:37", "linha": "220", "chegada": "16:26", "embarque": "R. São Gabriel, 1783", "desembarque": "Av. Luiz Bassete"},
            {"hora": "15:57", "linha": "220", "chegada": "16:46", "embarque": "R. São Gabriel, 1783", "desembarque": "Av. Luiz Bassete"},
            {"hora": "16:05", "linha": "213", "chegada": "17:00", "embarque": "R. Paraná, 1605", "desembarque": "Av. Luiz Bassete"},
            {"hora": "16:37", "linha": "220", "chegada": "17:26", "embarque": "R. São Gabriel, 1783", "desembarque": "Av. Luiz Bassete"},
            # ── Noite ────────────────────────────────────────────────────
            {"hora": "17:15", "linha": "213", "chegada": "18:10", "embarque": "R. Paraná, 1605", "desembarque": "Av. Luiz Bassete"},
            {"hora": "17:17", "linha": "220", "chegada": "18:06", "embarque": "R. São Gabriel, 1783", "desembarque": "Av. Luiz Bassete"},
            {"hora": "17:37", "linha": "220", "chegada": "18:26", "embarque": "R. São Gabriel, 1783", "desembarque": "Av. Luiz Bassete"},
            {"hora": "17:55", "linha": "213", "chegada": "18:50", "embarque": "R. Paraná, 1605", "desembarque": "Av. Luiz Bassete"},
            {"hora": "18:12", "linha": "220", "chegada": "19:01", "embarque": "R. São Gabriel, 1783", "desembarque": "Av. Luiz Bassete"},
            {"hora": "18:15", "linha": "213", "chegada": "19:10", "embarque": "R. Paraná, 1605", "desembarque": "Av. Luiz Bassete"},
            {"hora": "19:25", "linha": "213", "chegada": "20:20", "embarque": "R. Paraná, 1605", "desembarque": "Av. Luiz Bassete"},
            {"hora": "19:57", "linha": "220", "chegada": "20:46", "embarque": "R. São Gabriel, 1783", "desembarque": "Av. Luiz Bassete"},
            {"hora": "20:57", "linha": "220", "chegada": "21:46", "embarque": "R. São Gabriel, 1783", "desembarque": "Av. Luiz Bassete"},
            {"hora": "22:07", "linha": "220", "chegada": "22:56", "embarque": "R. São Gabriel, 1783", "desembarque": "Av. Luiz Bassete"},
            {"hora": "22:35", "linha": "213", "chegada": "23:30", "embarque": "R. Paraná, 1605", "desembarque": "Av. Luiz Bassete"},
            {"hora": "23:27", "linha": "220", "chegada": "00:16", "embarque": "R. São Gabriel, 1783", "desembarque": "Av. Luiz Bassete"},
        ],
    },
    "casa_faculdade": {
        "nome": "🏠→🎓 Casa → Faculdade",
        "horarios": [
            {"hora": "04:10", "linha": "220", "chegada": "04:49", "embarque": "R. Cira de O. Petrin, 622", "desembarque": "R. Álvaro Cechino, 69"},
            {"hora": "05:10", "linha": "220", "chegada": "05:49", "embarque": "R. Cira de O. Petrin, 622", "desembarque": "R. Álvaro Cechino, 69"},
            {"hora": "05:50", "linha": "220", "chegada": "06:29", "embarque": "R. Cira de O. Petrin, 622", "desembarque": "R. Álvaro Cechino, 69"},
            {"hora": "06:30", "linha": "220", "chegada": "07:09", "embarque": "R. Cira de O. Petrin, 622", "desembarque": "R. Álvaro Cechino, 69"},
            {"hora": "07:00", "linha": "220", "chegada": "07:39", "embarque": "R. Cira de O. Petrin, 622", "desembarque": "R. Álvaro Cechino, 69"},
            {"hora": "07:20", "linha": "220", "chegada": "07:59", "embarque": "R. Cira de O. Petrin, 622", "desembarque": "R. Álvaro Cechino, 69"},
            {"hora": "08:00", "linha": "220", "chegada": "08:39", "embarque": "R. Cira de O. Petrin, 622", "desembarque": "R. Álvaro Cechino, 69"},
            {"hora": "08:40", "linha": "220", "chegada": "09:19", "embarque": "R. Cira de O. Petrin, 622", "desembarque": "R. Álvaro Cechino, 69"},
            {"hora": "09:10", "linha": "220", "chegada": "09:49", "embarque": "R. Cira de O. Petrin, 622", "desembarque": "R. Álvaro Cechino, 69"},
            {"hora": "10:10", "linha": "220", "chegada": "10:49", "embarque": "R. Cira de O. Petrin, 622", "desembarque": "R. Álvaro Cechino, 69"},
            {"hora": "10:30", "linha": "220", "chegada": "11:09", "embarque": "R. Cira de O. Petrin, 622", "desembarque": "R. Álvaro Cechino, 69"},
            {"hora": "11:00", "linha": "220", "chegada": "11:39", "embarque": "R. Cira de O. Petrin, 622", "desembarque": "R. Álvaro Cechino, 69"},
            {"hora": "11:30", "linha": "220", "chegada": "12:09", "embarque": "R. Cira de O. Petrin, 622", "desembarque": "R. Álvaro Cechino, 69"},
            {"hora": "12:10", "linha": "220", "chegada": "12:49", "embarque": "R. Cira de O. Petrin, 622", "desembarque": "R. Álvaro Cechino, 69"},
            {"hora": "12:40", "linha": "220", "chegada": "13:19", "embarque": "R. Cira de O. Petrin, 622", "desembarque": "R. Álvaro Cechino, 69"},
            {"hora": "13:10", "linha": "220", "chegada": "13:49", "embarque": "R. Cira de O. Petrin, 622", "desembarque": "R. Álvaro Cechino, 69"},
            {"hora": "13:30", "linha": "220", "chegada": "14:09", "embarque": "R. Cira de O. Petrin, 622", "desembarque": "R. Álvaro Cechino, 69"},
            {"hora": "14:00", "linha": "220", "chegada": "14:39", "embarque": "R. Cira de O. Petrin, 622", "desembarque": "R. Álvaro Cechino, 69"},
            {"hora": "15:10", "linha": "220", "chegada": "15:49", "embarque": "R. Cira de O. Petrin, 622", "desembarque": "R. Álvaro Cechino, 69"},
            {"hora": "15:50", "linha": "220", "chegada": "16:29", "embarque": "R. Cira de O. Petrin, 622", "desembarque": "R. Álvaro Cechino, 69"},
            {"hora": "16:20", "linha": "220", "chegada": "16:59", "embarque": "R. Cira de O. Petrin, 622", "desembarque": "R. Álvaro Cechino, 69"},
            {"hora": "16:40", "linha": "220", "chegada": "17:19", "embarque": "R. Cira de O. Petrin, 622", "desembarque": "R. Álvaro Cechino, 69"},
            {"hora": "17:20", "linha": "220", "chegada": "17:59", "embarque": "R. Cira de O. Petrin, 622", "desembarque": "R. Álvaro Cechino, 69"},
            {"hora": "18:10", "linha": "220", "chegada": "18:49", "embarque": "R. Cira de O. Petrin, 622", "desembarque": "R. Álvaro Cechino, 69"},
            {"hora": "19:20", "linha": "220", "chegada": "19:59", "embarque": "R. Cira de O. Petrin, 622", "desembarque": "R. Álvaro Cechino, 69"},
            {"hora": "20:30", "linha": "220", "chegada": "21:09", "embarque": "R. Cira de O. Petrin, 622", "desembarque": "R. Álvaro Cechino, 69"},
            {"hora": "21:40", "linha": "220", "chegada": "22:19", "embarque": "R. Cira de O. Petrin, 622", "desembarque": "R. Álvaro Cechino, 69"},
            {"hora": "22:50", "linha": "220", "chegada": "23:29", "embarque": "R. Cira de O. Petrin, 622", "desembarque": "R. Álvaro Cechino, 69"},
        ],
    },
    "trabalho_casa": {
        "nome": "💼→🏠 Trabalho → Casa",
        "horarios": [
            # ── Manhã ────────────────────────────────────────────────────
            {"hora": "04:50", "linha": "220", "chegada": "05:26", "embarque": "R. Rui Barbosa, 261", "desembarque": "Av. Luiz Bassete"},
            {"hora": "05:30", "linha": "220", "chegada": "06:06", "embarque": "R. Rui Barbosa, 261", "desembarque": "Av. Luiz Bassete"},
            {"hora": "06:01", "linha": "213", "chegada": "06:40", "embarque": "Av. Brasil, 61", "desembarque": "Av. Luiz Bassete"},
            {"hora": "06:10", "linha": "220", "chegada": "06:46", "embarque": "R. Rui Barbosa, 261", "desembarque": "Av. Luiz Bassete"},
            {"hora": "06:30", "linha": "220", "chegada": "07:06", "embarque": "R. Rui Barbosa, 261", "desembarque": "Av. Luiz Bassete"},
            {"hora": "06:50", "linha": "220", "chegada": "07:26", "embarque": "R. Rui Barbosa, 261", "desembarque": "Av. Luiz Bassete"},
            {"hora": "07:01", "linha": "213", "chegada": "07:40", "embarque": "Av. Brasil, 61", "desembarque": "Av. Luiz Bassete"},
            {"hora": "07:20", "linha": "220", "chegada": "07:56", "embarque": "R. Rui Barbosa, 261", "desembarque": "Av. Luiz Bassete"},
            {"hora": "07:40", "linha": "220", "chegada": "08:16", "embarque": "R. Rui Barbosa, 261", "desembarque": "Av. Luiz Bassete"},
            {"hora": "07:51", "linha": "213", "chegada": "08:30", "embarque": "Av. Brasil, 61", "desembarque": "Av. Luiz Bassete"},
            {"hora": "08:11", "linha": "213", "chegada": "08:50", "embarque": "Av. Brasil, 61", "desembarque": "Av. Luiz Bassete"},
            {"hora": "08:30", "linha": "220", "chegada": "09:06", "embarque": "R. Rui Barbosa, 261", "desembarque": "Av. Luiz Bassete"},
            # ── Meio-dia ─────────────────────────────────────────────────
            {"hora": "09:00", "linha": "220", "chegada": "09:36", "embarque": "R. Rui Barbosa, 261", "desembarque": "Av. Luiz Bassete"},
            {"hora": "09:11", "linha": "213", "chegada": "09:50", "embarque": "Av. Brasil, 61", "desembarque": "Av. Luiz Bassete"},
            {"hora": "09:40", "linha": "220", "chegada": "10:16", "embarque": "R. Rui Barbosa, 261", "desembarque": "Av. Luiz Bassete"},
            {"hora": "10:00", "linha": "220", "chegada": "10:36", "embarque": "R. Rui Barbosa, 261", "desembarque": "Av. Luiz Bassete"},
            {"hora": "10:11", "linha": "213", "chegada": "10:50", "embarque": "Av. Brasil, 61", "desembarque": "Av. Luiz Bassete"},
            {"hora": "10:40", "linha": "220", "chegada": "11:16", "embarque": "R. Rui Barbosa, 261", "desembarque": "Av. Luiz Bassete"},
            {"hora": "11:40", "linha": "220", "chegada": "12:16", "embarque": "R. Rui Barbosa, 261", "desembarque": "Av. Luiz Bassete"},
            {"hora": "11:41", "linha": "213", "chegada": "12:20", "embarque": "Av. Brasil, 61", "desembarque": "Av. Luiz Bassete"},
            {"hora": "12:10", "linha": "220", "chegada": "12:46", "embarque": "R. Rui Barbosa, 261", "desembarque": "Av. Luiz Bassete"},
            {"hora": "12:30", "linha": "220", "chegada": "13:06", "embarque": "R. Rui Barbosa, 261", "desembarque": "Av. Luiz Bassete"},
            {"hora": "12:31", "linha": "213", "chegada": "13:10", "embarque": "Av. Brasil, 61", "desembarque": "Av. Luiz Bassete"},
            # ── Tarde ────────────────────────────────────────────────────
            {"hora": "13:00", "linha": "220", "chegada": "13:36", "embarque": "R. Rui Barbosa, 261", "desembarque": "Av. Luiz Bassete"},
            {"hora": "13:11", "linha": "213", "chegada": "13:50", "embarque": "Av. Brasil, 61", "desembarque": "Av. Luiz Bassete"},
            {"hora": "13:30", "linha": "220", "chegada": "14:06", "embarque": "R. Rui Barbosa, 261", "desembarque": "Av. Luiz Bassete"},
            {"hora": "14:01", "linha": "213", "chegada": "14:40", "embarque": "Av. Brasil, 61", "desembarque": "Av. Luiz Bassete"},
            {"hora": "14:40", "linha": "220", "chegada": "15:16", "embarque": "R. Rui Barbosa, 261", "desembarque": "Av. Luiz Bassete"},
            {"hora": "14:51", "linha": "213", "chegada": "15:30", "embarque": "Av. Brasil, 61", "desembarque": "Av. Luiz Bassete"},
            {"hora": "15:10", "linha": "220", "chegada": "15:46", "embarque": "R. Rui Barbosa, 261", "desembarque": "Av. Luiz Bassete"},
            {"hora": "15:31", "linha": "213", "chegada": "16:10", "embarque": "Av. Brasil, 61", "desembarque": "Av. Luiz Bassete"},
            {"hora": "15:50", "linha": "220", "chegada": "16:26", "embarque": "R. Rui Barbosa, 261", "desembarque": "Av. Luiz Bassete"},
            {"hora": "16:10", "linha": "220", "chegada": "16:46", "embarque": "R. Rui Barbosa, 261", "desembarque": "Av. Luiz Bassete"},
            {"hora": "16:21", "linha": "213", "chegada": "17:00", "embarque": "Av. Brasil, 61", "desembarque": "Av. Luiz Bassete"},
            {"hora": "16:50", "linha": "220", "chegada": "17:26", "embarque": "R. Rui Barbosa, 261", "desembarque": "Av. Luiz Bassete"},
            # ── Noite ────────────────────────────────────────────────────
            {"hora": "17:30", "linha": "220", "chegada": "18:06", "embarque": "R. Rui Barbosa, 261", "desembarque": "Av. Luiz Bassete"},
            {"hora": "17:31", "linha": "213", "chegada": "18:10", "embarque": "Av. Brasil, 61", "desembarque": "Av. Luiz Bassete"},
            {"hora": "17:50", "linha": "220", "chegada": "18:26", "embarque": "R. Rui Barbosa, 261", "desembarque": "Av. Luiz Bassete"},
            {"hora": "18:11", "linha": "213", "chegada": "18:50", "embarque": "Av. Brasil, 61", "desembarque": "Av. Luiz Bassete"},
            {"hora": "18:25", "linha": "220", "chegada": "19:01", "embarque": "R. Rui Barbosa, 261", "desembarque": "Av. Luiz Bassete"},
            {"hora": "18:31", "linha": "213", "chegada": "19:10", "embarque": "Av. Brasil, 61", "desembarque": "Av. Luiz Bassete"},
            {"hora": "19:41", "linha": "213", "chegada": "20:20", "embarque": "Av. Brasil, 61", "desembarque": "Av. Luiz Bassete"},
            {"hora": "20:10", "linha": "220", "chegada": "20:46", "embarque": "R. Rui Barbosa, 261", "desembarque": "Av. Luiz Bassete"},
            {"hora": "21:10", "linha": "220", "chegada": "21:46", "embarque": "R. Rui Barbosa, 261", "desembarque": "Av. Luiz Bassete"},
            {"hora": "22:20", "linha": "220", "chegada": "22:56", "embarque": "R. Rui Barbosa, 261", "desembarque": "Av. Luiz Bassete"},
            {"hora": "22:51", "linha": "213", "chegada": "23:30", "embarque": "Av. Brasil, 61", "desembarque": "Av. Luiz Bassete"},
            {"hora": "23:40", "linha": "220", "chegada": "00:16", "embarque": "R. Rui Barbosa, 261", "desembarque": "Av. Luiz Bassete"},
        ],
    },
}


# ── Formatação ───────────────────────────────────────────────────────────────


def proximos_onibus(trajeto_key: str, limite: int = 3) -> str:
    """Mostra os próximos N ônibus a partir da hora atual."""
    trajeto = HORARIOS[trajeto_key]
    hora_atual = datetime.now(TZ).strftime("%H:%M")

    proximos = [h for h in trajeto["horarios"] if h["hora"] >= hora_atual]

    titulo = trajeto["nome"]

    if not proximos:
        return f"{titulo}\n\n😴 Sem mais ônibus hoje."

    itens = proximos[:limite]
    linhas = [titulo, ""]
    for h in itens:
        linhas.append(
            f"  {h['hora']}  L.{h['linha']}  → {h['chegada']}\n"
            f"  📍 {h['embarque']} → {h['desembarque']}"
        )

    restantes = len(proximos) - len(itens)
    if restantes > 0:
        linhas.append(f"\n  +{restantes} ônibus restantes")

    return "\n".join(linhas)


def todos_horarios(trajeto_key: str) -> str:
    """Mostra todos os horários do dia, agrupados por linha."""
    trajeto = HORARIOS[trajeto_key]

    # Agrupa por linha
    por_linha: dict[str, dict] = {}
    for h in trajeto["horarios"]:
        linha = h["linha"]
        if linha not in por_linha:
            por_linha[linha] = {
                "horas": [],
                "embarque": h["embarque"],
                "desembarque": h["desembarque"],
            }
        por_linha[linha]["horas"].append(h["hora"])

    partes = [f"📋 {trajeto['nome']}", ""]

    for linha, dados in por_linha.items():
        horas = dados["horas"]
        partes.append(f"L.{linha} ({len(horas)} viagens)")
        # Formata em linhas de 6
        for i in range(0, len(horas), 6):
            partes.append("  " + "  ".join(horas[i : i + 6]))
        partes.append(f"  📍 {dados['embarque']}")
        partes.append(f"     → {dados['desembarque']}")
        partes.append("")

    return "\n".join(partes)


def resumo_trajetos() -> str:
    """Mostra o próximo ônibus de cada trajeto (visão geral compacta)."""
    hora_atual = datetime.now(TZ).strftime("%H:%M")
    linhas = [f"📋 Resumo — {hora_atual}\n"]

    for key, trajeto in HORARIOS.items():
        proximos = [h for h in trajeto["horarios"] if h["hora"] >= hora_atual]
        if proximos:
            h = proximos[0]
            linhas.append(
                f"{trajeto['nome']}\n"
                f"  {h['hora']}  L.{h['linha']}  → {h['chegada']}"
            )
        else:
            linhas.append(f"{trajeto['nome']}\n  😴 encerrado")

    return "\n\n".join(linhas)


# ── Teclados ─────────────────────────────────────────────────────────────────


def menu_keyboard(route=None, showing_all=False):
    """Monta teclado inline. Se route informado, adiciona botão Todos/Próximos."""
    buttons = []
    if route:
        if showing_all:
            buttons.append(
                [InlineKeyboardButton("⏭ Próximos", callback_data=f"bus_{route}")]
            )
        else:
            buttons.append(
                [InlineKeyboardButton("📋 Todos os horários", callback_data=f"busall_{route}")]
            )
    buttons.extend(
        [
            [
                InlineKeyboardButton("🏠→💼", callback_data="bus_casa_trabalho"),
                InlineKeyboardButton("💼→🎓", callback_data="bus_trabalho_faculdade"),
                InlineKeyboardButton("🎓→🏠", callback_data="bus_faculdade_casa"),
            ],
            [
                InlineKeyboardButton("🏠→🎓", callback_data="bus_casa_faculdade"),
                InlineKeyboardButton("💼→🏠", callback_data="bus_trabalho_casa"),
                InlineKeyboardButton("📋 Resumo", callback_data="bus_todos"),
            ],
        ]
    )
    return InlineKeyboardMarkup(buttons)


# ── Handlers Telegram ────────────────────────────────────────────────────────


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /start — se cadastrado, mostra menu. Se não, sugere cadastro.
    NOTA: O ConversationHandler de cadastro tem prioridade; este handler
    só é atingido se o ConversationHandler não capturou (i.e., user já cadastrado).
    """
    chat_id = update.effective_chat.id
    user = db.get_user(chat_id)

    if user and user["onboarding_completo"]:
        nome = user["nome"]
        await update.message.reply_text(
            f"🤖 Fala {nome}! Escolhe o trajeto:", reply_markup=menu_keyboard()
        )
    else:
        # Não deveria chegar aqui (ConversationHandler captura antes),
        # mas como fallback:
        await update.message.reply_text(
            "👋 Bem-vindo ao FAMus! Vamos fazer seu cadastro.\n"
            "Mande /start novamente para iniciar."
        )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    texto = (
        "📖 *Comandos*\n\n"
        "🎓 *Aulas*\n"
        "/aula — grade horária (hoje, amanhã, semana)\n\n"
        "📚 *FAM*\n"
        "/notas — boletim (1x/semana Free)\n"
        "/grade — atualizar grade do portal\n\n"
        "⭐ *Pro*\n"
        "/onibus — horários de ônibus\n"
        "/faltas — faltas por disciplina\n"
        "/simular — quanto preciso pra passar\n"
        "/dp — matérias reprovadas\n"
        "/atividades — atividades do portal\n\n"
        "💳 *Plano*\n"
        "/assinar — assinar plano Pro\n"
        "/plano — ver seu plano\n\n"
        "⚙️ *Geral*\n"
        "/start — menu principal\n"
        "/help — esta mensagem\n"
        "/config — ver seus dados\n"
        "/resetar — resetar cadastro\n"
        "/clear — limpar conversa com IA\n\n"
        "📬 *Contato*\n"
        "/suporte — pedir ajuda\n"
        "/sugestoes — enviar ideia\n\n"
        "_⭐ = exclusivo Pro_"
    )
    await update.message.reply_text(texto, parse_mode="Markdown")


async def cmd_onibus(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    db.log_evento(chat_id, "cmd_onibus")

    if not db.is_pro(chat_id):
        await update.message.reply_text(
            "⭐ Recurso exclusivo Pro!\n"
            "Use /assinar pra desbloquear (R$ 9,90/mês)\n"
            "7 dias grátis no cadastro!"
        )
        return

    user = db.get_user(chat_id)
    transporte = (user or {}).get("transporte", "sou")
    if transporte != "sou":
        transporte_labels = {"emtu": "EMTU / Intermunicipal", "carro": "Carro / Carona", "outro": "Outro"}
        label = transporte_labels.get(transporte, transporte)
        await update.message.reply_text(
            f"As rotas de ônibus SOU Americana não se aplicam ao seu caso "
            f"(transporte: {label}).\n\n"
            "Use /config pra ver seus dados ou /resetar e /start pra alterar.",
        )
        return

    await update.message.reply_text(
        resumo_trajetos(), reply_markup=menu_keyboard()
    )


async def cmd_trajeto(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    if not db.is_pro(chat_id):
        await update.message.reply_text(
            "⭐ Recurso exclusivo Pro!\n"
            "Use /assinar pra desbloquear (R$ 9,90/mês)\n"
            "7 dias grátis no cadastro!"
        )
        return

    comando = update.message.text.lstrip("/").split("@")[0]
    if comando in HORARIOS:
        await update.message.reply_text(
            proximos_onibus(comando), reply_markup=menu_keyboard(route=comando)
        )


async def callback_botao(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    data = query.data

    # busall_casa_trabalho → todos os horários
    if data.startswith("busall_"):
        route = data[7:]
        if route in HORARIOS:
            texto = todos_horarios(route)
            kb = menu_keyboard(route=route, showing_all=True)
            try:
                await query.edit_message_text(texto, reply_markup=kb)
            except BadRequest:
                pass
        return

    if not data.startswith("bus_"):
        return

    trajeto = data[4:]
    if trajeto == "todos":
        texto = resumo_trajetos()
        kb = menu_keyboard()
    elif trajeto in HORARIOS:
        texto = proximos_onibus(trajeto)
        kb = menu_keyboard(route=trajeto)
    else:
        return

    try:
        await query.edit_message_text(texto, reply_markup=kb)
    except BadRequest:
        pass


async def cmd_clear(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Apaga as últimas mensagens do chat."""
    chat_id = update.message.chat_id
    msg_id = update.message.message_id
    count = 0
    for i in range(msg_id, max(msg_id - 100, 0), -1):
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=i)
            count += 1
        except Exception:
            pass
    msg = await update.effective_chat.send_message(f"🗑 {count} mensagens apagadas.")
    await asyncio.sleep(2)
    try:
        await msg.delete()
    except Exception:
        pass


async def mensagem_generica(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    user_tg = update.effective_user
    db.registrar_lead(chat_id, username=getattr(user_tg, 'username', None), primeiro_nome=getattr(user_tg, 'first_name', None))

    # Se estamos aguardando input especial (email, suporte, sugestão), não processar como IA
    import monitor
    if monitor._aguardando_email.get(chat_id) or monitor._aguardando_texto.get(chat_id):
        return

    # Gate de cadastro: se não registrado, manda cadastrar
    if not db.is_registered(chat_id):
        await update.message.reply_text(
            "Primeiro faça seu cadastro com /start 👆"
        )
        return

    db.log_evento(chat_id, "msg_ia")
    from gemini import perguntar
    from famus import responder

    texto = update.message.text
    extra = None
    loading_msg = None

    # Se pede atividades, roda o scraper e alimenta o Gemini
    t = texto.lower()
    if any(p in t for p in ("atividade", "tarefa", "portal")):
        loading_msg = await update.message.reply_text("🔄 Consultando portal FAM...")
        try:
            from monitor import _scrape_atividades
            loop = asyncio.get_event_loop()
            atividades = await loop.run_in_executor(None, _scrape_atividades, chat_id)
            if atividades:
                partes = ["ATIVIDADES DO PORTAL FAM:"]
                for i, at in enumerate(atividades, 1):
                    titulo = at.get('titulo', 'N/A')
                    disc = at.get('disciplina', '')
                    prazo = (at.get('prazo', '') or '').replace('\n', ' ').strip()
                    sit = (at.get('situacao', '') or '').replace('\n', ' ').strip()
                    partes.append(f"{i}. {titulo} | {disc} | Prazo: {prazo} | {sit}")
                extra = "\n".join(partes)
            else:
                extra = "ATIVIDADES DO PORTAL FAM: Não foi possível acessar ou não há atividades."
        except Exception:
            extra = "ATIVIDADES DO PORTAL FAM: Erro ao consultar o portal."

    # Gemini AI
    loop = asyncio.get_event_loop()
    resposta = await loop.run_in_executor(None, perguntar, texto, chat_id, extra)

    if loading_msg:
        try:
            await loading_msg.delete()
        except Exception:
            pass

    if resposta:
        await update.message.reply_text(resposta, parse_mode="HTML")
        return

    # Fallback: pattern matching (se Gemini falhar)
    entendeu = await responder(update, context)
    if entendeu:
        return

    await update.message.reply_text(
        "Estou com dificuldade para processar no momento. Tente novamente em alguns segundos ou use /help para ver os comandos disponíveis.",
    )


def registrar_handlers(app: Application) -> None:
    """Registra todos os handlers de ônibus na Application."""
    # NOTA: /start agora é tratado pelo ConversationHandler de cadastro (registrado em monitor.py)
    # Este cmd_start só é chamado como fallback para usuários já cadastrados
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("clear", cmd_clear))
    app.add_handler(CommandHandler("onibus", cmd_onibus))
    for trajeto_key in HORARIOS:
        app.add_handler(CommandHandler(trajeto_key, cmd_trajeto))
    app.add_handler(CallbackQueryHandler(callback_botao, pattern="^bus"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, mensagem_generica))
