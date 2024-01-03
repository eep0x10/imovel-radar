import requests
import json
import pandas as pd
import googlemaps

# Setup GoogleMaps API
google_maps_api_key = 'AIzaSyChU6cb0pDKZ8y7YbZ6dc2OjmVo8A2BQlE'
gmaps = googlemaps.Client(key=google_maps_api_key)

# Verificar se o arquivo Excel já existe
excel_filename = 'resultados_quintoandar.xlsx'
try:
    existing_df = pd.read_excel(excel_filename)
    existing_ids = set(existing_df['_id'])
except FileNotFoundError:
    existing_df = pd.DataFrame()
    existing_ids = set()


# Linha Vermelha
tatuape1 = ["Tatuapé",-23.525958119495357,-23.559753874385716,-46.554870541873115,-46.587829526248115,-23.54285599694054,-46.571350034060615]
belem1 = ["Belem",-23.52579663898413,-23.559592435369122,-46.57117305459483,-46.60413203896983,-23.542694537176626,-46.58765254678233]
bMooca1 = ["Bresser Mooca",-23.53141064001946,-23.56520499365195,-46.5876387199463,-46.6205977043213,-23.548307816835703,-46.6041182121338]
pedroII1 = ["Pedro II",-23.531384751255526,-23.565179111541955,-46.60482116821592,-46.63778015259092,-23.54828193139874,-46.62130066040342]

Lvermelha_QuintoAndar=[tatuape1,belem1,bMooca1,pedroII1]

tatuape2=["Tatuapé",-23.565573743672587,-46.6237413722269,-23.53083516662427,-46.59026740372104]
belem2=["Belem",-23.565573743672587,-46.6237413722269,-23.53083516662427,-46.59026740372104]
bMooca2 = ["Bresser Mooca",-23.565573743672587,-46.6237413722269,-23.53083516662427,-46.59026740372104]
pedroII2 = ["Pedro II",-23.567109027274284,-46.64340600361652,-23.532370855967116,-46.60993203511066]
Lvermelha_Loft=[tatuape2,belem2,bMooca2,pedroII2]

c_min=150000
c_max=330000
a_min=35
a_max=70
quartos=2
banheiro=1
vagas=1
perto_metro=15

def filtros():
  print("[+] Filtros:",)
  print("   - Área min:",a_min,"m2")
  print("   - Área max:",a_max,"m2")
  print("   - Custo min:","R$"+str(int(c_min/1000))+"k")
  print("   - Custo max:","R$"+str(int(c_max/1000))+"k")
  print("   - Quartos:",quartos)
  print("   - Banheiros:",banheiro)
  print("   - Vagas:",vagas)
  print("   - Perto Metro:",perto_metro,"mins")

def get_nearest_metro_station(address):
    try:
        geocode_result = gmaps.geocode(address)
        location = geocode_result[0]['geometry']['location']
        nearest_station = gmaps.places_nearby(location, type='subway_station', rank_by='distance')

        if nearest_station['results']:
            station_name = nearest_station['results'][0]['name']
            station_location = nearest_station['results'][0]['geometry']['location']

            # Calcular a distância a pé
            walking_directions = gmaps.directions(location, station_location, mode='walking')
            walking_time = walking_directions[0]['legs'][0]['duration']['text']

            # Extrair apenas o número de minutos
            walking_time_minutes = int(walking_time.split()[0])
            return station_name, walking_time_minutes
        else:
            return "---", None

    except Exception as e:
        print(f"Erro ao obter estação de metrô: {e}")
        return None, None

def check_floor_limit(link_id):
    # Verificar se o termo "Até 3° andar" está presente na resposta da requisição GET
    try:
        response = requests.get(link_id)
        if "3° andar" in response.text:
            return True
        else:
            return False
    except Exception as e:
        print(f"Erro ao verificar limite de andar: {e}")
        return False

def compara_listas(n1, n2):
    set_n1 = set(n1)
    set_n2 = set(n2)

    valores_n1_nao_em_n2 = set_n1 - set_n2
    valores_n2_nao_em_n1 = set_n2 - set_n1
    valores_iguais = set_n1.intersection(set_n2)

    return list(valores_n1_nao_em_n2), list(valores_n2_nao_em_n1), list(valores_iguais)

# QUINTO ANDAR
def get_imoveis_quintoAndar(nome,bounds_north,bounds_south,bounds_east,bounds_west,center_lat,center_lng):
  print("[+] Obtendo dados QUINTO_ANDAR:",nome)
  
  burp0_url = "https://www.quintoandar.com.br:443/api/yellow-pages/v2/search"
  burp0_headers = {
  "X-Instana-T": "b8f42a4c5dd6ff7",
  "Sec-Ch-Ua": "\"Chromium\";v=\"117\", \"Not;A=Brand\";v=\"8\"",
  "Sec-Ch-Ua-Mobile": "?0",
  "X-Instana-L": "1,correlationType=web;correlationId=b8f42a4c5dd6ff7",
  "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.5938.63 Safari/537.36",
  "Content-Type": "text/plain;charset=UTF-8",
  "Accept": "application/p_click_version.V3.4+p_click_sale_version.V1+json",
  "Sec-Ch-Ua-Platform": "\"Windows\"",
  "Origin": "https://www.quintoandar.com.br",
  "Sec-Fetch-Site": "same-origin",
  "Sec-Fetch-Mode": "cors",
  "Sec-Fetch-Dest": "empty",
  "Accept-Encoding": "gzip, deflate, br",
  "Accept-Language": "en-US,en;q=0.9"}
  
  burp0_json={"business_context": "SALE", "filters": 
  {"area": 
    {
        "max_area": a_max,
        "min_area": a_min},
    "availability": "any",
    "cost": {"cost_type": "sale_price",
            "max_value": c_max,
            "min_value": c_min},
    "country_code": "BR",
    "house_type": ["Apartamento", "StudioOuKitchenette"],
    "map": {"bounds_east": bounds_east, "bounds_north": bounds_north, "bounds_south": bounds_south, "bounds_west": bounds_west, "center_lat": center_lat, "center_lng": center_lng},
    "min_bedrooms": quartos, "min_parking_spaces": vagas,
    "near_subway":True,
    "occupancy": "any",
    "offset": 0, "page_size": 1000,
    "sorting": {"criteria": "sale_price", "order": "desc"}},
              "force_raw_search": False,
              "relax_query": False,
              "return": ["id", "coverImage", "rent", "totalCost", "salePrice", "iptuPlusCondominium", "area", "imageList", "imageCaptionList", "address", "regionName", "city", "visitStatus", "activeSpecialConditions", "type", "forRent", "forSale", "isPrimaryMarket", "bedrooms", "parkingSpaces", "listingTags", "yield", "yieldStrategy", "neighbourhood", "categories", "bathrooms", "isFurnished", "installations"],
              "search_query_context": "unknown"}

  r=requests.post(burp0_url, headers=burp0_headers, json=burp0_json)
  return r

def extract_data_from_json_quintoAndar(json_data):
    try:
        data = json.loads(json_data)
        hits = data.get('hits', {}).get('hits', [])

        # Extrair _ids, salePrice, iptuPlusCondominium, area, address e outros parâmetros adicionais
        result_data = []
        for hit in hits:
          listing_tags = hit.get('fields', {}).get('listingTags', [])
            
            # Verificar se 'BUY_RENTED' não está presente em listingTags
          if 'BUY_RENTED' not in listing_tags:
            item_data = {
                'origem': f"QuintoAndar",
                'link_id': f"https://www.quintoandar.com.br/imovel/{hit.get('_id')}/comprar/",
                '_id': hit.get('_id'),
                'salePrice': hit.get('_source', {}).get('salePrice'),
                'iptuPlusCondominium': hit.get('_source', {}).get('iptuPlusCondominium'),
                'area': hit.get('_source', {}).get('area'),
                'address': hit.get('_source', {}).get('address'),
                'regionName': hit.get('_source', {}).get('regionName'),
                'city': hit.get('_source', {}).get('city'),
                'visitStatus': hit.get('_source', {}).get('visitStatus'),
                'type': hit.get('_source', {}).get('type'),
                'forSale': hit.get('_source', {}).get('forSale'),
                'bedrooms': hit.get('_source', {}).get('bedrooms'),
                'parkingSpaces': hit.get('_source', {}).get('parkingSpaces'),
                'bathrooms': hit.get('_source', {}).get('bathrooms'),
                'installations': hit.get('_source', {}).get('installations'),
                'isFurnished': hit.get('_source', {}).get('isFurnished'),
                'listingTags': hit.get('fields', {}).get('listingTags')
            }
            result_data.append(item_data)
        num=len(result_data)
        return result_data,num
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON: {e}")
        return num
    
# LOFT
def get_imoveis_loft(nome,neLatBoundary,neLngBoundary,swLatBoundary,swLngBoundary):
  print("[+] Obtendo dados LOFT:",nome)
  burp0_url = "https://landscape-api.loft.com.br:443/listing/v2/search?areaMax="+str(a_max)+"&areaMin="+str(a_min)+"&bedrooms="+str(quartos)+"&cities%5B%5D=sao+paulo%2C+sp&hitsPerPage=100008&neLatBoundary="+str(neLatBoundary)+"&neLngBoundary="+str(neLngBoundary)+"&orderBy%5B%5D=rankB&parkingSpots="+str(vagas)+"&priceMax="+str(c_max)+"&swLatBoundary="+str(swLatBoundary)+"&swLngBoundary="+str(swLngBoundary)+""
  burp0_headers = {
    "Sec-Ch-Ua": "\"Chromium\";v=\"119\", \"Not?A_Brand\";v=\"24\"",
    "Accept": "application/json, text/plain, */*",
    "X-Origin": "http://loft-website-sales.loft.com.br",
    "Sec-Ch-Ua-Mobile": "?0",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.6045.159 Safari/537.36",
    "Loftuserid": "36644831-8514-44a7-b130-01c0e9c1bb36",
    "Sec-Ch-Ua-Platform": "\"Windows\"",
    "Origin": "https://loft.com.br",
    "Sec-Fetch-Site": "same-site",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Dest": "empty",
    "Accept-Language": "en-US,en;q=0.9",
    "Priority": "u=1, i"}
  r=requests.get(burp0_url, headers=burp0_headers)
  return r

def extract_data_from_json_loft(json_data):
    # Carregando o JSON
    data = json.loads(json_data)

    # Criando uma lista de dicionários com as informações desejadas
    table_data = []
    for listing in data['listings']:
        address = listing['address']
        #facets = listing['facets']
        tax=listing['complexFee']
        if listing['propertyTax'] > 0:
          tax+=listing['propertyTax']

        table_data.append({
            'origem': f"Loft",
            'link_id': f"https://loft.com.br/imovel/{listing['id']}",
            'id': listing['id'],
            'price': listing['price'],
            'complexFee': tax,
            'area': listing['area'],
            'streetFullName': address['streetFullName'],
            'neighborhood': address['neighborhood'],
            'city': address['city'],
            'isRentable': listing['isRentable'],
            'type': address['type'],
            'status': listing['status'],
            'bedrooms': listing['bedrooms'],
            'parkingSpots': listing['parkingSpots'],
            'restrooms': listing['restrooms'],
            'amenities': listing['amenities'],
            #'unitFeatures': listing['unitFeatures']
        })

    num=len(table_data)
    return table_data,num

filtros()
#########################################################################
# EXTRAIR DADOS
extracted_data_QuintoAndar=[]
extracted_data_Loft=[]


num=0
for i in Lvermelha_QuintoAndar:
  r=get_imoveis_quintoAndar(i[0],i[1],i[2],i[3],i[4],i[5],i[6])
  json_data = r.text
  extracted_data_QuintoAndar += extract_data_from_json_quintoAndar(json_data)[0]
  num0 = extract_data_from_json_quintoAndar(json_data)[1]
  print("[!] Imoveis encontrados:",num0)
  num+=num0
#########################################################################
num=0
for i in Lvermelha_Loft:
  r2=get_imoveis_loft(i[0],i[1],i[2],i[3],i[4])
  json_data = r2.text
  extracted_data_Loft += extract_data_from_json_loft(json_data)[0]
  num0 = extract_data_from_json_loft(json_data)[1]
  print("[!] Imoveis encontrados:",num0)
  num+=num0
#########################################################################
# CRIAR DATAFRAME
df1 = pd.DataFrame(extracted_data_QuintoAndar)
df2 = pd.DataFrame(extracted_data_Loft)

column_mapping = {
  'id': '_id',
  'price': 'salePrice',
  'complexFee':'iptuPlusCondominium',
  'streetFullName':'address',
  'neighborhood':'regionName',
  'isRentable':'visitStatus',
  'status':'forSale',
  'parkingSpots':'parkingSpaces',
  'restrooms':'bathrooms',
  'amenities':'installations'
}
df2 = df2.rename(columns=column_mapping)
df = df1.combine_first(df2)
column_order = ["origem","_id","link_id","area","address","regionName","city","type","forSale","visitStatus","bedrooms","bathrooms","parkingSpaces","installations","isFurnished","listingTags","salePrice","iptuPlusCondominium"]
df=df[column_order]

tmp=len(df['_id'])
print(df)
print("Total:",tmp)
#########################################################################

#########################################################################
# LIMPAR DATAFRAME
# Removendo linhas duplicadas com base no '_id'
print("[X] Removendo duplicados...")
df = df.drop_duplicates(subset='_id', keep='first')
print("[!] -",str(tmp-len(df['_id'])))

#########################################################################
# Remover linhas com iptuPlusCondominium maior que 650
print("[X] Removendo imóveis com custo mensal > 580 / > 7000 anual...")
df = df[df['iptuPlusCondominium'] <= 580]
print("[!] -",str(tmp-len(df['_id'])))

#########################################################################

# Verificar andar limite e remover linhas correspondentes
print("[X] Removendo imóveis até o 3* Andar...")
df['_id'] = df['_id'].astype(str)
df['remove'] = df['link_id'].apply(check_floor_limit)
df = df[~df['remove']]
# Remover colunas auxiliares
df.drop(['remove'], axis=1, inplace=True)
print("[!] -",str(tmp-len(df['_id'])))

#########################################################################
# Adicionando colunas para estação de metrô e tempo a pé
df['nearestMetroStation'] = ""
df['walkingTimeToMetro'] = ""

# Preenchendo colunas com dados do Google Maps
print("[!] Calculando tempo até o metro mais próximo...")
for index, row in df.iterrows():
    address = row['address'] + ', ' + row['regionName'] + ', ' + row['city']
    nearest_station, walking_time = get_nearest_metro_station(address)

    df.at[index, 'nearestMetroStation'] = nearest_station
    df.at[index, 'walkingTimeToMetro'] = walking_time

# Remover linhas com tempo até o metrô maior que 15 minutos
print("[X] Removendo imóveis +15min até o metro...")
df = df[df['walkingTimeToMetro'] <= perto_metro]
print("[!] -",str(tmp-len(df['_id'])))

#########################################################################
# Total de Imóveis encontrados dentro dos requisitos
print("[+] Total:",len(df['_id']))
#########################################################################

# Validar com o antigo excel
actual_ids=set(df['_id'])
existing_ids = [str(valor) for valor in existing_ids]
actual_ids = [str(valor) for valor in actual_ids]

resultados = compara_listas(existing_ids, actual_ids)
print("Valores removidos:", resultados[0])
print("Valores adicionados:", resultados[1])
print("Valores iguais:", resultados[2])

#########################################################################
# Adicionar colunas com contas e estatísticas
df['custo/Metro'] = df['salePrice'] / df['area']
df['custo/Ano'] = df['iptuPlusCondominium'] * 12
df['Financiamento'] = df['salePrice'] - 140000
df['CustoTotalMensal+Financiamento8anos'] = df['iptuPlusCondominium'] + df['Financiamento']/96


#df['Visitado'] = 'Não' #FAZER COM QUE O PROGRAMA SALVE O STATUS DA AVALIACAO ANTERIOR, BOM RUIM OU NÃO

# Adicionando coluna 'status'
if existing_df.empty:
  df['status'] = 'NOVO'
else:
  df.loc[df['_id'].isin(resultados[0]), 'status'] = 'REMOVIDO'
  df.loc[df['_id'].isin(resultados[1]), 'status'] = 'NOVO'
  df.loc[df['_id'].isin(resultados[2]), 'status'] = 'FIXO'
#########################################################################

#########################################################################
# Exportando DataFrame para Excel
df.to_excel(excel_filename, index=False)
print(f"Resultados exportados para {excel_filename}")
#########################################################################










