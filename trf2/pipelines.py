# Define your item pipelines here
#
# Don't forget to add your pipeline to the ITEM_PIPELINES setting
# See: https://docs.scrapy.org/en/latest/topics/item-pipeline.html


# useful for handling different item types with a single interface
from itemadapter import ItemAdapter

# trf2/pipelines.py

import json


class JsonWriterPipeline:
    def open_spider(self, spider):
        # Você pode querer um arquivo por spider ou um arquivo geral.
        # Para este exemplo, um arquivo por item, nomeado pelo número do processo.
        # Se você quiser um único arquivo JSON com uma lista de todos os processos,
        # a abordagem seria diferente (acumular itens e escrever no close_spider).
        spider.logger.info("JsonWriterPipeline aberta.")

    def close_spider(self, spider):
        spider.logger.info("JsonWriterPipeline fechada.")

    def process_item(self, item, spider):
        # Usar o numero_processo_raw para nomear o arquivo
        raw_num = item.get('numero_processo_raw', 'desconhecido')
        output_filename = f"{raw_num}.json"

        # Convertendo o Item do Scrapy para um dicionário antes de salvar
        # para garantir que todos os dados sejam serializáveis.
        line = json.dumps(dict(item), ensure_ascii=False, indent=4)
        with open(output_filename, 'w', encoding='utf-8') as f:
            f.write(line)
        spider.logger.info(f"Dados do processo {raw_num} salvos em {output_filename}")
        return item