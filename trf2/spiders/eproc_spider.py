# trf2/spiders/eproc_spider.py

import scrapy
import re
import json
import html
from urllib.parse import urljoin, urlparse, parse_qs
from trf2.items import ProcessoTrf2Item  # Importa o Item que definimos
from lxml import html as lxml_html



class EprocProcessoParser:
    def __init__(self, html_content, response_url):  # Removido session, adicionado response_url
        self.tree = lxml_html.fromstring(html_content)
        self.response_url = response_url  # URL base para resolver links relativos, se necessário

    def extrair_assuntos(self):
        rows = self.tree.xpath(
            '//table[contains(@class, "infraTable") and contains(@class, "table-not-hover")]'
            '//tr[@data-assunto-principal="true"]'
        )
        if not rows:
            return {}
        row = rows[0]
        cols = row.xpath('.//td')
        return {"assunto_principal": {"codigo": cols[0].text_content().strip(),
                                      "descricao": cols[1].text_content().strip()}}

    def extrair_informacoes_processo(self):
        def ext(path):
            v = self.tree.xpath(path)
            return v[0].strip() if v else "N/A"

        return {
            "numero_processo": ext('//span[@id="txtNumProcesso"]/text()'),
            "classe_acao": ext('//span[@id="txtClasse"]/text()'),
            "competencia": ext('//span[@id="txtCompetencia"]/text()'),
            "data_autuacao": ext('//span[@id="txtAutuacao"]/text()').split(' ')[0],
            "situacao_processo": ext('//span[@id="txtSituacao"]/text()'),
            "orgao_julgador": ext('//span[@id="txtOrgaoJulgador"]/text()'),
            "juiz": ext('//span[@id="txtMagistrado"]/text()')
        }

    def _extrair_partes_de_spans(self, spans_all):
        print(f"--- DEBUG: Entrando em _extrair_partes_de_spans com {len(spans_all)} spans ---") # DEBUG
        autores = []
        advs_autor = []
        reus = []
        advs_reu = []
        for idx, span in enumerate(spans_all): # 'span' é o elemento <span class="infraNomeParte">
            nome_original = span.text_content().strip()
            nome_final_com_documento = nome_original # Inicializa com o nome original

            print(f"--- DEBUG: _extrair_partes_de_spans - Span {idx} - Nome Original: '{nome_original}' ---") # DEBUG
            
            if 'MINISTÉRIO PÚBLICO' in nome_original.upper() or 'OS MESMOS' in nome_original.upper():
                print(f"--- DEBUG: Ignorando entidade não parte: {nome_original}")
                continue
            
            # Extrair o número do documento (CPF/CNPJ)
            # O span do documento é geralmente um irmão do span do nome ou está próximo dentro da mesma célula (td)
            # Vamos procurar dentro do elemento pai (a célula <td>)
            celula_pai = span.getparent()
            documento_numero = None
            if celula_pai is not None:
                # Tenta encontrar o span do documento pelo title="Copiar CPF/CNPJ" dentro da célula
                # Usamos .// para buscar em qualquer nível dentro da célula, caso haja alguma div extra.
                # Pegamos o primeiro, pois deve haver um por parte principal.
                doc_span_list = celula_pai.xpath('.//span[@title="Copiar CPF/CNPJ"]')
                if doc_span_list:
                    documento_numero_bruto = doc_span_list[0].text_content()
                    if documento_numero_bruto:
                        documento_numero = documento_numero_bruto.strip()
                        print(f"--- DEBUG: _extrair_partes_de_spans - Span {idx} - Documento encontrado: '{documento_numero}' ---")
                        nome_final_com_documento = f"{nome_original} -- {documento_numero}"
                else:
                    print(f"--- DEBUG: _extrair_partes_de_spans - Span {idx} - Nenhum span de documento encontrado para '{nome_original}' ---")
            else:
                print(f"--- DEBUG: _extrair_partes_de_spans - Span {idx} - Não foi possível obter a célula pai para '{nome_original}' ---")

            qual = span.getnext()
            direcao = 'passivo' # Default
            if qual is not None and qual.text_content() is not None and 'AUTOR' in qual.text_content().upper():
                direcao = 'ativo'
            elif qual is not None and qual.text_content() is not None and 'RÉU' in qual.text_content().upper(): 
                direcao = 'passivo' 

            print(f"--- DEBUG: _extrair_partes_de_spans - Span {idx} - Qual: {qual.text_content().strip() if qual is not None and qual.text_content() is not None else 'N/A'}, Direção: {direcao} ---")
            print(f"--- DEBUG: _extrair_partes_de_spans - Span {idx} - Nome Final (com doc): '{nome_final_com_documento}' ---")


            advs = []
            if celula_pai is not None: 
                print(f"--- DEBUG: _extrair_partes_de_spans - Span {idx} - Parent tag para advs: {celula_pai.tag if celula_pai is not None else 'N/A'} ---")
                for a in celula_pai.xpath('.//a[@onmouseover]'): 
                    txts = a.xpath('preceding-sibling::text()')
                    prefixo = txts[-1].strip() if txts else ''
                    reg = a.text_content().strip()
                    adv_full = f"{prefixo} - {reg}" if prefixo else reg
                    advs.append(adv_full)
                    print(f"--- DEBUG: _extrair_partes_de_spans - Span {idx} - Advogado encontrado: {adv_full} ---")
            
            if direcao == 'ativo':
                if nome_final_com_documento not in autores: # Verifica usando o nome já com documento
                    autores.append(nome_final_com_documento)
                    advs_autor.extend(advs)
            else: 
                if nome_final_com_documento not in reus: # Verifica usando o nome já com documento
                    reus.append(nome_final_com_documento)
                    advs_reu.extend(advs)
        
        advs_autor = list(dict.fromkeys(advs_autor))
        advs_reu = list(dict.fromkeys(advs_reu))
        resultado = {}
        if autores:
            resultado['Polo_ativo'] = {"autores": autores, "advogados_autor": advs_autor}
        if reus:
            resultado['Polo_passivo'] = {"reus": reus, "advogados_reu": advs_reu}
        print(f"--- DEBUG: _extrair_partes_de_spans - Resultado: {resultado} ---") 
        return resultado

    def extrair_informacoes_adicionais(self, ajax_html_content):
        """
        Extrai os campos da seção 'Informações Adicionais' do HTML (string) 
        retornado pelo AJAX. Este HTML é o conteúdo da div 'fldInformacoesAdicionais_content'.
        """
        if not ajax_html_content:
            print("--- DEBUG PARSER_INFO_ADIC: Conteúdo HTML para Informações Adicionais está vazio. ---")
            return {}

        try:
            # O ajax_html_content já deve ser o HTML limpo que preenche a div de conteúdo
            tree = lxml_html.fromstring(ajax_html_content)
        except Exception as e:
            print(f"--- DEBUG PARSER_INFO_ADIC: Erro ao parsear HTML das Informações Adicionais com lxml: {e} ---")
            print(f"--- DEBUG PARSER_INFO_ADIC: HTML problemático (primeiros 300 chars): {ajax_html_content[:300]} ---")
            return {}
        
        informacoes = {}
        # Os itens estão em <div class="col-md-4 ..."><div class="row"><span>Label</span><span>Valor</span></div></div>
        # O seletor abaixo pega cada <div class="row"> que contém um par de label/valor.
        # O HTML fornecido mostra que o conteúdo AJAX já é o <div id="fldInformacoesAdicionais_content"> preenchido.
        # Dentro dele, há um <div class="row pl-5 pr-5"> e depois os <div class="col-md-4...">
        
        # Seleciona cada "célula" contendo um par label-valor
        celulas_info = tree.xpath('.//div[contains(@class, "col-md-4") and contains(@class, "col-sm-6") and contains(@class, "col-12") and ./div[@class="row"]]')

        print(f"--- DEBUG PARSER_INFO_ADIC: Encontrados {len(celulas_info)} blocos (células) de informação. ---")

        labels_desejados = [ # Baseado na sua lista
            "Ação Coletiva de subst. processual", "Agravo Retido", "Doença Grave",
            "Grande devedor", "Idoso", "Justiça Gratuita",
            "Penhora no rosto dos autos", "Penhora/apreensão de bens",
            "Pessoa com deficiência", "Petição Urgente", "Possui bem associado",
            "Vista Ministério Público", "Valor da Causa"
        ]

        for celula in celulas_info:
            # Dentro de cada célula, esperamos um <div class="row">
            # e dentro deste, dois <span> (ou um span e um span com link/imagem)
            label_node = celula.xpath('.//div[@class="row"]/span[1]')
            valor_node = celula.xpath('.//div[@class="row"]/span[2]')

            if label_node and valor_node:
                label_bruto = label_node[0].text_content()
                label = label_bruto.strip().rstrip(':') if label_bruto else ""

                valor_span_content = valor_node[0] # Este é o segundo span <span class="col text-left...">
                
                # Lógica de extração de valor, considerando estruturas aninhadas
                if label == "Valor da Causa":
                    # Formato: <a><img></a> R$ VALOR
                    # Pega o último nó de texto direto do span de valor
                    textos_diretos = valor_span_content.xpath("./text()")
                    valor_limpo = "".join(t.strip() for t in textos_diretos if t.strip())
                    if not valor_limpo: # Fallback caso o texto esteja em outro lugar
                        valor_limpo = valor_span_content.xpath("normalize-space(.)").strip()
                elif label in ["Anexos Eletrônicos", "Benefício Prev.", "Conciliações Virtuais", "Usuários com Vista ao Processo"]:
                    # Tenta pegar texto de um link <a> dentro, senão o texto geral do span
                    link_interno_text = valor_span_content.xpath(".//a/text()")
                    if link_interno_text and link_interno_text[0].strip():
                        valor_limpo = link_interno_text[0].strip()
                    else: # Fallback para texto geral do span, normalizado
                        valor_limpo = valor_span_content.xpath("normalize-space(.)").strip()
                        # Se tiver imagem de "atualizar" e depois "0" ou nada, pode precisar de mais lógica
                        if valor_limpo == "" and valor_span_content.xpath(".//img[contains(@src, 'atualizar.gif')]"):
                            # Se só tem a img de atualizar e nenhum texto visível, pode ser "0" ou "Não verificado"
                            # O HTML para "Conciliações Virtuais: 0" é <a ...>0</a>, então o xpath acima deve pegar.
                            pass # Deixa vazio se não encontrar texto explícito

                else: # Para campos simples como "Sim", "Não", "Deferida"
                    valor_limpo = valor_span_content.xpath("normalize-space(.)").strip()
                
                if label in labels_desejados:
                    informacoes[label] = valor_limpo
                    print(f"--- DEBUG PARSER_INFO_ADIC: Extraído: '{label}' = '{valor_limpo}' ---")
            else:
                print(f"--- DEBUG PARSER_INFO_ADIC: Não encontrou label/valor em: {lxml_html.tostring(celula, encoding='unicode')} ---")
        
        if not informacoes:
            print("--- DEBUG PARSER_INFO_ADIC: Nenhuma informação adicional foi extraída. Verifique os seletores e o HTML de entrada.")

        return informacoes
    
    def extrair_partes_e_representantes_main_page(self):
        """Extrai apenas as partes visíveis na página principal."""
        spans_main = self.tree.xpath('//span[contains(@class, "infraNomeParte")]')
        return self._extrair_partes_de_spans(spans_main)

    def get_ajax_params_for_hidden_parts(self, html_text_main_page):
        """
        Extrai os parâmetros necessários para a chamada AJAX das partes ocultas.
        Retorna um dicionário com os parâmetros ou None se não encontrados.
        """
        m_param = re.search(r"carregarPartes\('([^']+)','([^']+)','([^']+)'\)", html_text_main_page)
        m_hash = re.search(r"carregar_partes_ocultas_processo&hash=([0-9a-f]+)", html_text_main_page)

        if m_param and m_hash:
            id_proc, id_pessoa, tipo_parte = m_param.groups()
            hash_ocultas = m_hash.group(1)
            ajax_url = (
                f"https://eproc.trf2.jus.br/eproc/controlador_ajax.php"
                f"?acao_ajax=carregar_partes_ocultas_processo&hash={hash_ocultas}"
            )
            payload = {
                "idProcesso": id_proc,
                "idPessoaCarregada": id_pessoa,
                "tipoParte": tipo_parte,
                "sinPermiteConsultaReuSobMonitoramento": "N",
                "sinPermiteCadastroReuSobMonitoramento": "N"
            }
            return {"url": ajax_url, "payload": payload}
        return None

    def parse_hidden_parts_from_ajax_response(self, ajax_html_content):
        """Parseia o HTML da resposta AJAX e extrai as partes."""
        print("--- DEBUG: Entrando em parse_hidden_parts_from_ajax_response ---")
        if not ajax_html_content:
            print("--- DEBUG: Conteúdo AJAX vazio ou None ---")
            return {}
        try:
            print(f"--- DEBUG: Conteúdo AJAX Original (primeiros 500 chars): {ajax_html_content[:500]} ---")
            html_parser_lxml = lxml_html.HTMLParser(encoding='iso-8859-1')  # Ou o encoding correto

            # Envolver em <root> para garantir um único elemento raiz para lxml
            wrapped_html_content = f"<root>{ajax_html_content}</root>"
            frag_root = lxml_html.fromstring(wrapped_html_content, parser=html_parser_lxml)

            # --- INÍCIO: Diagnóstico Adicional do LXML e XPath ---
            print(
                f"--- DEBUG: Estrutura parseada pelo LXML (dentro de <root>):\n{lxml_html.tostring(frag_root, pretty_print=True, encoding='unicode')} ---")

            # Teste 1: Encontrar QUALQUER span
            any_spans = frag_root.xpath('//span')
            print(f"--- DEBUG: Teste 1 - Qualquer span encontrado (//span): {len(any_spans)} ---")
            if any_spans:
                print(
                    f"--- DEBUG: Teste 1 - Atributos do primeiro span encontrado: {any_spans[0].attrib if len(any_spans) > 0 else 'N/A'} ---")

            # Teste 2: Tentar XPath com correspondência exata da classe
            exact_class_spans = frag_root.xpath('//span[@class="infraNomeParte"]')
            print(
                f"--- DEBUG: Teste 2 - Spans com classe EXATA 'infraNomeParte' (//span[@class=\"infraNomeParte\"]): {len(exact_class_spans)} ---")

            # Teste 3: Seu XPath original com contains
            contains_class_spans = frag_root.xpath('//span[contains(@class, "infraNomeParte")]')
            print(
                f"--- DEBUG: Teste 3 - Spans com classe CONTENDO 'infraNomeParte' (//span[contains(@class, \"infraNomeParte\")]): {len(contains_class_spans)} ---")

            # Teste 4: Tentar um XPath mais específico se a estrutura for conhecida
            # Exemplo: encontrar spans com a classe dentro da tabela específica (se houver apenas uma)
            spans_in_table = frag_root.xpath(
                '//table[@id="tblPartesERepresentantes"]//span[contains(@class, "infraNomeParte")]')
            print(
                f"--- DEBUG: Teste 4 - Spans 'infraNomeParte' dentro da tabela 'tblPartesERepresentantes': {len(spans_in_table)} ---")
            # --- FIM: Diagnóstico Adicional do LXML e XPath ---

            # Use o XPath que funcionar melhor (provisoriamente o Teste 3, seu original)
            fragment_spans = contains_class_spans  # ou exact_class_spans se funcionar melhor

            if fragment_spans:
                for i, span_element in enumerate(fragment_spans):
                    print(
                        f"--- DEBUG: Span AJAX {i} selecionado para extração: {lxml_html.tostring(span_element, pretty_print=True, encoding='unicode')} ---")
            else:
                print(f"--- DEBUG: Nenhum span 'infraNomeParte' foi efetivamente selecionado para extração. ---")

            return self._extrair_partes_de_spans(fragment_spans)
        except Exception as e:
            print(f"--- DEBUG: Erro crítico ao parsear fragmento AJAX ou nos testes XPath: {e} ---")
            import traceback
            traceback.print_exc()  # Imprime o stack trace completo do erro
            return {}

    def extrair_movimentacoes(self):
        tabela = self.tree.xpath('//table[contains(@id, "tblEventos")]')
        if not tabela:
            print("--- DEBUG PARSER MOVIMENTACOES: Tabela de eventos 'tblEventos' não encontrada.")
            return {}
        
        from urllib.parse import urljoin 

        movs = {}
        linhas_movimentacao = tabela[0].xpath('.//tr[position()>0]')
        
        if not linhas_movimentacao:
            print("--- DEBUG PARSER MOVIMENTACOES: Nenhuma linha de movimentação encontrada na tabela 'tblEventos' (excluindo header).")
            return {}

        for idx, row in enumerate(linhas_movimentacao):
            cols = row.xpath('.//td')
            # Agora precisamos de pelo menos 5 colunas para acessar cols[4]
            if len(cols) < 5: # AJUSTADO: Verificar se temos pelo menos 5 colunas
                print(f"--- DEBUG PARSER MOVIMENTACOES: Linha {idx} tem menos de 5 colunas, pulando.")
                continue
            
            # Coluna 1 (índice 1) -> Data do Evento
            data_hora_evento_raw = cols[1].text_content().strip()
            data_evento = data_hora_evento_raw.split(' ')[0]

            # Coluna 2 (índice 2) -> Descrição do Evento
            descricao_html_bruto = lxml_html.tostring(cols[2], encoding='unicode').strip()
            descricao_texto_limpo = re.sub(r'<[^>]+>', ' ', descricao_html_bruto)
            descricao_texto_limpo = re.sub(r'\s+', ' ', descricao_texto_limpo).strip()

            # Coluna 4 (índice 4) -> Documentos
            documentos = []
            # A célula que contém os documentos é cols[4] (a quinta célula)
            celula_documentos = cols[4] # <<< AJUSTADO AQUI
            
            links_de_documento = celula_documentos.xpath('.//a[@class="infraLinkDocumento"]')
            
            if not links_de_documento:
                print(f"--- DEBUG PARSER MOVIMENTACOES: Nenhum link 'infraLinkDocumento' na coluna de documentos da mov. {idx}.")

            for link_tag in links_de_documento:
                nome_doc_bruto = link_tag.get('title', '') 
                nome_doc = nome_doc_bruto.split('\n')[0].strip() if nome_doc_bruto else "Nome não disponível"
                if not nome_doc and link_tag.text_content():
                    nome_doc = link_tag.text_content().strip()

                url_doc_relativo = link_tag.get('href')
                
                if url_doc_relativo:
                    try:
                        url_doc_absoluto = urljoin(self.response_url, url_doc_relativo)
                    except NameError: 
                        print("--- ERROR PARSER MOVIMENTACOES: urljoin não definida! Verifique a importação de urllib.parse.urljoin ---")
                        url_doc_absoluto = url_doc_relativo 
                else:
                    url_doc_absoluto = "URL não disponível"
                    #print(f"--- DEBUG PARSER MOVIMENTACOES: Link na mov. {idx} sem href: {nome_doc}")

                documentos.append({"nome": nome_doc, "URL": url_doc_absoluto})
            
            movs[str(idx)] = {
                "data_movimentacao": data_evento, 
                "Descricao": descricao_texto_limpo,
                "Documentos": documentos
            }
            #print(f"--- DEBUG PARSER MOVIMENTACOES: Mov. {idx} processada. Data: {data_evento}, Desc: '{descricao_texto_limpo[:50]}...', Docs: {len(documentos)}")

        if not movs:
            print("--- DEBUG PARSER MOVIMENTACOES: Nenhuma movimentação foi extraída da tabela 'tblEventos'.")
        return movs

    def extract_all(self, partes_principais, partes_ocultas_ajax=None):
        info = self.extrair_informacoes_processo()
        assuntos = self.extrair_assuntos()
        movs = self.extrair_movimentacoes()

        # Combinar partes principais e ocultas
        # Esta lógica de combinação pode precisar de ajuste para evitar duplicatas
        # ou para estruturar corretamente se houver sobreposição.
        # Por ora, vamos fazer um merge simples.
        partes_combinadas = {}
        if 'Polo_ativo' in partes_principais:
            partes_combinadas.setdefault('Polo_ativo', {'autores': [], 'advogados_autor': []})
            partes_combinadas['Polo_ativo']['autores'].extend(partes_principais['Polo_ativo'].get('autores', []))
            partes_combinadas['Polo_ativo']['advogados_autor'].extend(
                partes_principais['Polo_ativo'].get('advogados_autor', []))
        if partes_ocultas_ajax and 'Polo_ativo' in partes_ocultas_ajax:
            partes_combinadas.setdefault('Polo_ativo', {'autores': [], 'advogados_autor': []})
            partes_combinadas['Polo_ativo']['autores'].extend(partes_ocultas_ajax['Polo_ativo'].get('autores', []))
            partes_combinadas['Polo_ativo']['advogados_autor'].extend(
                partes_ocultas_ajax['Polo_ativo'].get('advogados_autor', []))

        if 'Polo_passivo' in partes_principais:
            partes_combinadas.setdefault('Polo_passivo', {'reus': [], 'advogados_reu': []})
            partes_combinadas['Polo_passivo']['reus'].extend(partes_principais['Polo_passivo'].get('reus', []))
            partes_combinadas['Polo_passivo']['advogados_reu'].extend(
                partes_principais['Polo_passivo'].get('advogados_reu', []))
        if partes_ocultas_ajax and 'Polo_passivo' in partes_ocultas_ajax:
            partes_combinadas.setdefault('Polo_passivo', {'reus': [], 'advogados_reu': []})
            partes_combinadas['Polo_passivo']['reus'].extend(partes_ocultas_ajax['Polo_passivo'].get('reus', []))
            partes_combinadas['Polo_passivo']['advogados_reu'].extend(
                partes_ocultas_ajax['Polo_passivo'].get('advogados_reu', []))

        # Deduplicar listas após o merge
        if 'Polo_ativo' in partes_combinadas:
            partes_combinadas['Polo_ativo']['autores'] = list(dict.fromkeys(partes_combinadas['Polo_ativo']['autores']))
            partes_combinadas['Polo_ativo']['advogados_autor'] = list(
                dict.fromkeys(partes_combinadas['Polo_ativo']['advogados_autor']))
        if 'Polo_passivo' in partes_combinadas:
            partes_combinadas['Polo_passivo']['reus'] = list(dict.fromkeys(partes_combinadas['Polo_passivo']['reus']))
            partes_combinadas['Polo_passivo']['advogados_reu'] = list(
                dict.fromkeys(partes_combinadas['Polo_passivo']['advogados_reu']))

        resultado = {"Mais_detalhes": info}
        if assuntos:
            resultado["Assuntos"] = assuntos
        resultado.update(partes_combinadas)  # Usa as partes combinadas
        resultado["Movimentos"] = movs
        # Não vamos retornar JSON aqui, mas um dicionário. A serialização para JSON
        # pode ser feita pelo Scrapy Feed Exporters ou um Pipeline.
        return resultado


# --- FIM: Adaptação da classe EprocProcessoParser ---

class EprocTrf2Spider(scrapy.Spider):
    name = "eproc_trf2"
    allowed_domains = ["eproc.trf2.jus.br"]  # Opcional, mas bom para segurança
    base_url = "https://eproc.trf2.jus.br/eproc/"

    # Cookies e Headers (do seu script original)
    # Em Scrapy, é comum definir headers por requisição ou em settings.py
    # Os cookies podem ser passados no primeiro Request ou gerenciados pelo Scrapy.
    custom_headers = {
        "User-Agent": "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:137.0) Gecko/20100101 Firefox/137.0",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "pt-BR,pt;q=0.8,en-US;q=0.5,en;q=0.3",
        # "Accept-Encoding": "gzip, deflate, br, zstd", # Scrapy geralmente lida com encoding
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",  # Para a primeira requisição. Pode mudar para 'same-origin' depois.
        "Sec-Fetch-User": "?1",
    }

    initial_cookies = {
        "_ga_CHRMKCJTEH": "deleted",
        "_ga": "GA1.3.2142236572.1749072110",
        "PHPSESSID": "om75dmkttd242aqo00jo82g4g1",  # Este é geralmente dinâmico
        "dicas_vistas": "[1]",
        "data_ultima_dica_vista": "16/06/2025",  # Ajuste se necessário
        "EPROC_A_TRF2_6342187bc0a248b388a58f8028e8927c1408f3c70f61f77496ecc66ac89baf62":
            "0001m399wkctbw3kgj2zq5gk335427ad4a835640e0784ae422f1dfc5a183416158cfefd017d9732087229084c3168833acea4c33848cf545ba6a2e50d764e73602cefab6a469dcee34c2f2adf7",
        "EPROC_D_TRF2_6342187bc0a248b388a58f8028e8927c1408f3c70f61f77496ecc66ac89baf62":
            "0001m399wkctbw3kgj2zq5gk3355379cf90e819723f8368639823d2726faf373844440921c75d50f6e0a875dd6a0c3aefd6190acb32b023346966099ecdef6b6f4872340f78e5e18f80328357a",
    }

    # Lista padrão de processos. Pode ser sobrescrita via argumento ou script.
    #default_processos = ["5015384-20.2021.4.02.5001"]

    def __init__(self, processos=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if processos:
            self.processos = processos if isinstance(processos, list) else [processos]
        '''else:
            self.processos = self.default_processos'''

    def start_requests(self):
        """Enfileira uma requisição inicial para cada processo."""
        for proc in self.processos:
            self.logger.info(f"Iniciando scraping para o processo {proc}")
            yield scrapy.Request(
                url=self.base_url,
                headers=self.custom_headers,
                cookies=self.initial_cookies,
                dont_filter=True,
                callback=self.parse_initial_page,
                cb_kwargs={"processo": proc},
            )

    def parse_initial_page(self, response, processo):
        """
        Callback para a resposta da página inicial. Extrai o hash de pesquisa.
        """
        self.logger.info(f"Página inicial carregada: {response.url}")
        # hash_listagem = parse_qs(urlparse(response.url).query).get("hash", [None])[0] # get com default
        # self.logger.info(f"Hash de listagem: {hash_listagem}") # Não usado no seu fluxo principal

        # Extrair o hash de pesquisa do formulário
        # Usando seletores Scrapy (CSS ou XPath)
        hash_pesquisa = response.xpath(
            '//form[contains(@action, "processo_pesquisa_rapida")]//input[@name="hash"]/@value').get()
        # Ou, se o hash estiver na action URL como no seu regex:
        if not hash_pesquisa:
            match = re.search(r'processo_pesquisa_rapida&hash=([0-9a-f]+)', response.text)
            if match:
                hash_pesquisa = match.group(1)

        if not hash_pesquisa:
            self.logger.error("Não foi possível encontrar o hash de pesquisa no HTML da listagem.")
            return

        #self.logger.info(f"Hash de pesquisa rápida encontrado: {hash_pesquisa}")

        # Preparar e fazer a requisição POST para buscar o processo
        search_url = f"{self.base_url}controlador.php?acao=processo_pesquisa_rapida&hash={hash_pesquisa}"

        payload = {
            "txtNumProcessoPesquisaRapida": processo,
            "btnPesquisaRapidaSubmit": "",  # Valor exato pode ser importante
            "acao_retorno_pesquisa_rapida": "painel_adv_listar",  # Ou o que for necessário
            # "hash": hash_pesquisa # Se o hash também for necessário no payload POST
        }

        #self.logger.info(f"Enviando POST para {search_url} com payload: {payload}")

        # Atualizando headers para a requisição POST
        post_headers = self.custom_headers.copy()
        post_headers["Sec-Fetch-Site"] = "same-origin"  # Geralmente muda após a primeira navegação
        post_headers["Origin"] = f"{urlparse(self.base_url).scheme}://{urlparse(self.base_url).netloc}"
        post_headers["Referer"] = response.url

        yield scrapy.FormRequest(
            url=search_url,
            formdata=payload,
            headers=post_headers,
            callback=self.parse_process_page,
            cb_kwargs={"processo_numero_raw": processo.replace(".", "").replace("-", "")},
        )

    def parse_informacoes_adicionais_ajax(self, response, item, parser):
          #self.logger.info(f"Callback parse_informacoes_adicionais_ajax: Resposta AJAX recebida (Status: {response.status}).")

          # ANTECIPAR O PROBLEMA: Verificar se esta resposta também é uma string HTML "escapada"
          ajax_content_type = response.headers.get('Content-Type', b'').decode('utf-8', 'ignore')
          #self.logger.info(f"--- DEBUG INFO_ADIC_AJAX: Content-Type: {ajax_content_type} ---")
          #self.logger.info(f"--- DEBUG INFO_ADIC_AJAX: repr(response.text[:100]): {repr(response.text[:100])} ---")

          cleaned_html_info_adicionais = response.text # Suposição inicial

          # Se o Content-Type for text/html mas o repr indicar que é uma string literal escapada:
          if cleaned_html_info_adicionais.startswith('"') and cleaned_html_info_adicionais.endswith('"'):
              #self.logger.info("--- DEBUG INFO_ADIC_AJAX: Resposta parece ser string literal. Tentando json.loads(). ---")
              try:
                  cleaned_html_info_adicionais = json.loads(cleaned_html_info_adicionais)
                  #self.logger.info("--- DEBUG INFO_ADIC_AJAX: HTML de Info Adicionais limpo com json.loads(). ---")
              except json.JSONDecodeError as e:
                  self.logger.error(f"--- DEBUG INFO_ADIC_AJAX: Falha ao limpar HTML de Info Adicionais com json.loads(): {e}. Usando texto original.")
          
          # Salvar para depuração
          # with open(f"debug_info_adicionais_ajax_{item['numero_processo_raw']}.html", "w", encoding="utf-8") as f:
          #     f.write(cleaned_html_info_adicionais)
          # self.logger.info(f"Conteúdo AJAX de Informações Adicionais salvo para depuração.")

          dados_info_adicional = parser.extrair_informacoes_adicionais(cleaned_html_info_adicionais)
          
          if dados_info_adicional:
              item['info_adicional'] = dados_info_adicional
              #self.logger.info(f"Informações Adicionais extraídas: {len(dados_info_adicional)} campos.")
          else:
              #self.logger.warning("Nenhuma Informação Adicional foi extraída pelo parser.")
              item['info_adicional'] = {} 

          #self.logger.info(f"Item final pronto para ser enviado: {item['numero_processo_raw']}")
          yield item 

    def _extrair_url_informacoes_adicionais(self, main_page_html_text, main_page_response):
          """
          Extrai a URL para carregar as Informações Adicionais.
          main_page_html_text: O conteúdo HTML da página principal do processo.
          main_page_response: O objeto Response da página principal, para usar response.urljoin().
          """
          #self.logger.debug("Tentando extrair URL das Informações Adicionais.")
          # O onclick está em: <legend id="legInfAdicional" ... onclick="carregarInformacoesAdicionais('URL', {PARAMS});">
          onclick_attr_match = re.search(
              r'<legend[^>]*id="legInfAdicional"[^>]*onclick="([^"]+)"',
              main_page_html_text,
              re.IGNORECASE
          )
          if not onclick_attr_match:
              self.logger.warning("Atributo onclick da legenda 'legInfAdicional' (Informações Adicionais) não encontrado.")
              return None
          
          onclick_text = onclick_attr_match.group(1)
          
          # Extrair a URL da função JavaScript carregarInformacoesAdicionais('URL', ...)
          url_match = re.search(r"carregarInformacoesAdicionais\s*\(\s*'([^']+)'", onclick_text)
          if url_match:
              ajax_url_rel = url_match.group(1)
              ajax_url_rel_unescaped = html.unescape(ajax_url_rel) # Trata &amp; etc.
              ajax_url_abs = main_page_response.urljoin(ajax_url_rel_unescaped)
              self.logger.info(f"URL para Informações Adicionais encontrada: {ajax_url_abs}")
              return ajax_url_abs
          else:
              self.logger.warning("URL dentro de carregarInformacoesAdicionais (Informações Adicionais) não encontrada.")
              return None

    def parse_process_page(self, response, processo_numero_raw):
        """
        Callback para a página de detalhes do processo (após o redirect do POST).
        Aqui instanciamos o parser e extraímos os dados.
        """
        #self.logger.info(f"Página de detalhes do processo carregada: {response.url}")
        #self.logger.info(f"Status code: {response.status}")

        parser = EprocProcessoParser(response.text, response.url)

        item = ProcessoTrf2Item()
        item['numero_processo_raw'] = processo_numero_raw

        # 1. Extrair partes da página principal
        partes_principais = parser.extrair_partes_e_representantes_main_page()
        ajax_params_partes = parser.get_ajax_params_for_hidden_parts(response.text)
        url_info_adicionais = self._extrair_url_informacoes_adicionais(response.text, response)
        
        if ajax_params_partes:
            self.logger.info(
                f"Parâmetros AJAX encontrados. Fazendo requisição para partes ocultas: {ajax_params_partes['url']}")

            ajax_headers = self.custom_headers.copy()
            ajax_headers["Accept"] = "*/*"  # Comum para AJAX
            ajax_headers["X-Requested-With"] = "XMLHttpRequest"  # Comum para AJAX
            ajax_headers["Sec-Fetch-Site"] = "same-origin"
            ajax_headers["Origin"] = f"{urlparse(self.base_url).scheme}://{urlparse(self.base_url).netloc}"
            ajax_headers["Referer"] = response.url

            yield scrapy.FormRequest(
                url=ajax_params_partes['url'],
                formdata=ajax_params_partes['payload'],
                headers=ajax_headers,
                callback=self.parse_ajax_hidden_parts,
                cb_kwargs={
                      'item': item,
                      'parser': parser,
                      'partes_principais': partes_principais,
                      'url_info_adicionais': url_info_adicionais
                  }
            )
        elif url_info_adicionais: # Não há AJAX de partes, mas há de info adicionais
              #self.logger.info("Nenhum AJAX para Partes, mas prosseguindo para Informações Adicionais.")
              # Popular o item com as partes principais (não AJAX) e outros dados da pág. principal
              # Se extract_all pode ser chamado com partes_ocultas_ajax=None:
              temp_data = parser.extract_all(partes_principais=partes_principais, partes_ocultas_ajax=None)
              item['mais_detalhes'] = temp_data.get("Mais_detalhes")
              item['assuntos'] = temp_data.get("Assuntos")
              item['polo_ativo'] = temp_data.get("Polo_ativo")
              item['polo_passivo'] = temp_data.get("Polo_passivo")
              item['movimentos'] = temp_data.get("Movimentos")
              item['info_adicional'] = {} # Inicializa como vazio

              yield scrapy.Request(
                  url_info_adicionais,
                  callback=self.parse_informacoes_adicionais_ajax,
                  headers=self.custom_headers, # Use headers apropriados
                  cb_kwargs={'item': item, 'parser': parser}
              )
        else:
            #self.logger.info("Nenhum parâmetro AJAX para partes ocultas encontrado. Prosseguindo sem elas.")
            # Se não houver chamada AJAX, finalize a extração com o que temos
            item_data = parser.extract_all(partes_principais=partes_principais, partes_ocultas_ajax=None)

            item = ProcessoTrf2Item()
            item['mais_detalhes'] = item_data.get("Mais_detalhes")
            item['assuntos'] = item_data.get("Assuntos")
            item['polo_ativo'] = item_data.get("Polo_ativo")
            item['polo_passivo'] = item_data.get("Polo_passivo")
            item['movimentos'] = item_data.get("Movimentos")
            item['numero_processo_raw'] = processo_numero_raw
            item['info_adicional'] = {}
            yield item

    def parse_ajax_hidden_parts(self, response, item, parser, partes_principais, url_info_adicionais):
          #self.logger.info(f"Callback parse_ajax_hidden_parts: Resposta AJAX para Partes recebida (Status: {response.status}).")
          
          cleaned_html_partes = ""
          try:
              # Limpa a string HTML da resposta AJAX das Partes (como feito anteriormente)
              cleaned_html_partes = json.loads(response.text)
              #self.logger.info("parse_ajax_hidden_parts: HTML das Partes limpo com json.loads().")
          except json.JSONDecodeError:
              #self.logger.error("parse_ajax_hidden_parts: Falha ao limpar HTML das Partes com json.loads(). Usando response.text diretamente.")
              cleaned_html_partes = response.text

          partes_ocultas_ajax = parser.parse_hidden_parts_from_ajax_response(cleaned_html_partes)
          
          # Atualiza o item com os dados que dependem das partes (principais e ocultas)
          # É importante que o parser.extract_all ou os métodos chamados aqui
          # não tentem preencher 'info_adicional' ainda.
          # Vamos assumir que o extract_all do seu parser agora é mais flexível
          # ou que você está preenchendo o item de forma granular.

          # Exemplo de como preencher granularmente:
          item['mais_detalhes'] = parser.extrair_informacoes_processo() # Se ainda não preenchido
          item['assuntos'] = parser.extrair_assuntos() # Se ainda não preenchido
          item['movimentos'] = parser.extrair_movimentacoes() # Se ainda não preenchido
          
          # Combina partes principais e ocultas para os polos
          polos_combinados = {}
          # Lógica de merge de partes_principais e partes_ocultas_ajax (adaptado do seu extract_all)
          if 'Polo_ativo' in partes_principais or (partes_ocultas_ajax and 'Polo_ativo' in partes_ocultas_ajax):
              polos_combinados.setdefault('Polo_ativo', {'autores': [], 'advogados_autor': []})
              if 'Polo_ativo' in partes_principais:
                  polos_combinados['Polo_ativo']['autores'].extend(partes_principais['Polo_ativo'].get('autores', []))
                  polos_combinados['Polo_ativo']['advogados_autor'].extend(partes_principais['Polo_ativo'].get('advogados_autor', []))
              if partes_ocultas_ajax and 'Polo_ativo' in partes_ocultas_ajax:
                  polos_combinados['Polo_ativo']['autores'].extend(partes_ocultas_ajax['Polo_ativo'].get('autores', []))
                  polos_combinados['Polo_ativo']['advogados_autor'].extend(partes_ocultas_ajax['Polo_ativo'].get('advogados_autor', []))
              # Deduplicar
              polos_combinados['Polo_ativo']['autores'] = list(dict.fromkeys(polos_combinados['Polo_ativo']['autores']))
              polos_combinados['Polo_ativo']['advogados_autor'] = list(dict.fromkeys(polos_combinados['Polo_ativo']['advogados_autor']))

          if 'Polo_passivo' in partes_principais or (partes_ocultas_ajax and 'Polo_passivo' in partes_ocultas_ajax):
              polos_combinados.setdefault('Polo_passivo', {'reus': [], 'advogados_reu': []})
              if 'Polo_passivo' in partes_principais:
                  polos_combinados['Polo_passivo']['reus'].extend(partes_principais['Polo_passivo'].get('reus', []))
                  polos_combinados['Polo_passivo']['advogados_reu'].extend(partes_principais['Polo_passivo'].get('advogados_reu', []))
              if partes_ocultas_ajax and 'Polo_passivo' in partes_ocultas_ajax:
                  polos_combinados['Polo_passivo']['reus'].extend(partes_ocultas_ajax['Polo_passivo'].get('reus', []))
                  polos_combinados['Polo_passivo']['advogados_reu'].extend(partes_ocultas_ajax['Polo_passivo'].get('advogados_reu', []))
              # Deduplicar
              polos_combinados['Polo_passivo']['reus'] = list(dict.fromkeys(polos_combinados['Polo_passivo']['reus']))
              polos_combinados['Polo_passivo']['advogados_reu'] = list(dict.fromkeys(polos_combinados['Polo_passivo']['advogados_reu']))
          
          item['polo_ativo'] = polos_combinados.get('Polo_ativo')
          item['polo_passivo'] = polos_combinados.get('Polo_passivo')
          # Certifique-se que outros campos que o extract_all preenchia (exceto info_adicional)
          # sejam preenchidos aqui ou em parse_process_page.

          if url_info_adicionais:
              self.logger.info(f"Fazendo requisição para Informações Adicionais: {url_info_adicionais}")
              yield scrapy.Request(
                  url_info_adicionais,
                  callback=self.parse_informacoes_adicionais_ajax,
                  headers=self.custom_headers, 
                  cb_kwargs={'item': item, 'parser': parser} 
              )
          else:
              self.logger.warning("URL para Informações Adicionais não disponível. Finalizando item sem elas.")
              item['info_adicional'] = {} # Garante que o campo existe
              yield item