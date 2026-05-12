"""Event-driven бэктестер Zenith-Control Ultimate.

Пакет реализует оффлайновую симуляцию торговой системы (v1/v2) на 1m-свечах
Binance (или синтетическом ГСЧ) с реалистичными комиссиями Bybit V5 linear
(taker 0.055%, maker 0.02%), 1-тиковым slippage на market и PostOnly
skip-on-cross для лимитных заявок. Только stdlib, без тяжёлых числовых
библиотек (чистый Python: statistics, math, list comprehensions).
"""
