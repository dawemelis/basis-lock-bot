# BASIS-LOCK bot (cloud)

Paper-trading bot schvaleny Court of Claude: long spot BTC + short CME
futures, sklizen basis uzamcene pri vstupu. Nasazeni jen kdyz cista
anualizovana basis > T-bill + 2 p.b. Jinak je bot T-bill portfolio.

Bezi kazdou hodinu pres GitHub Actions (.github/workflows/bot.yml),
stav uklada do basis_lock.db a bot_log.txt.

PAPER TRADING ONLY - zadne realne penize, zadne API klice.
