# Define here the models for your scraped items
#
# See documentation in:
# https://docs.scrapy.org/en/latest/topics/items.html

# trf2/items.py

import scrapy

class ProcessoTrf2Item(scrapy.Item):
    # Campos baseados na saída do seu EprocProcessoParser
    mais_detalhes = scrapy.Field()       # Corresponde a "Mais_detalhes"
    info_adicional = scrapy.Field()
    assuntos = scrapy.Field()            # Corresponde a "Assuntos"
    polo_ativo = scrapy.Field()          # Corresponde a "Polo_ativo"
    polo_passivo = scrapy.Field()        # Corresponde a "Polo_passivo"
    movimentos = scrapy.Field()          # Corresponde a "Movimentos"
    numero_processo_raw = scrapy.Field() # <--- ADICIONE ESTA LINHA
