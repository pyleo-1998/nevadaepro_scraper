import re
import json
import pathlib
import requests
from bs4 import BeautifulSoup
from typing import Optional,Mapping 
from urllib.parse import quote_plus
from headers import download_files_headers,pagination_headers



class Nevadaepro_Scraper:
    
    def __init__(self, proxy:dict = {}) -> None:
        self.session = requests.Session()
        self.session.proxies.update(proxy)
        self.all_extracted_data = []
        self.current_directory = pathlib.Path.cwd()
        
    def __save_files(self, response:Optional[Mapping[requests.session,dict]],bid_id:str ,file_name:str) -> None:
        
        file_path = self.current_directory / bid_id / file_name
        if not file_path.parent.exists():
            file_path.parent.mkdir(parents=True, exist_ok=True)
            
        if isinstance(response,requests.models.Response):
            with open(file_path,"wb") as html_file:
                html_file.write(response.content)
        
        elif isinstance(response,dict):
            with open(file_path,"w") as json_file:
                json_formatted_str = json.dumps(response, indent=2)
                json_file.write(json_formatted_str)
            
    def __remove_unwanted_char(self, raw_string:str) -> str:
        filtered_string = re.sub(r"[\n+\t+:+]"," ",raw_string)
        filtered_string = re.sub(r"\s+"," ",filtered_string)
        return filtered_string.strip()
    
    def download_files(self, file_name:str, _csrf:str, bid_id:str, downloadFileNbr:str, refer_link:str) -> None:
        
        url = "https://nevadaepro.com/bso/external/bidDetail.sdo"

        payload=f'_csrf={_csrf}&mode=download&bidId={bid_id}&docId={bid_id}&currentPage=1&querySql=&downloadFileNbr={downloadFileNbr}&itemNbr=undefined&parentUrl=close&fromQuote=&destination='
        download_files_headers['referer'] = refer_link
        response = self.session.post( url,headers=download_files_headers,  data=payload)
        self.__save_files(response,bid_id,file_name)
    
    def __extract_info_from_details_html_page(self, detail_page_uri:str, doc_id:str) -> dict:
        detail_page_url = "https://nevadaepro.com"+detail_page_uri 
        detail_page_response = self.session.get(detail_page_url)
        soup_detail_page = BeautifulSoup(detail_page_response.content, 'html.parser')
        csrf_token_detail_page = soup_detail_page.select('input[name="_csrf"]')[0].get('value')

        self.__save_files(detail_page_response,doc_id,f"detail_page_{doc_id}.html")
                    
        raw_detail_page_table_data = soup_detail_page.select('table > tr:nth-child(3) > td > table > tr')
        extracted_data_from_detail_page = {}
        break_on_bill_to_address = False
        for row_index,row_details_page_data in enumerate(raw_detail_page_table_data):
            if row_index ==0:
                continue

            for column_index,column_details_page_data in enumerate(row_details_page_data.select('td'),1):
                column_detail_html_page_data = column_details_page_data.get_text().strip()
                if column_detail_html_page_data.find('Pre Bid Conference')!=-1 or column_detail_html_page_data.find('Bulletin Desc:')!=-1:

                    for detail_table_raw_row_html_tag in column_details_page_data.select('tr'):
                        detail_table_raw_column_html_tag =  detail_table_raw_row_html_tag.select('td')
                        extracted_data_from_detail_page[self.__remove_unwanted_char(detail_table_raw_column_html_tag[0].get_text())] = self.__remove_unwanted_char(detail_table_raw_column_html_tag[1].get_text())

                    continue
                
                if column_index%2==0:
                    extracted_data_from_detail_page[self.__remove_unwanted_char(key)] = self.__remove_unwanted_char(column_details_page_data.get_text())
                    
                    if key == 'Bill-to Address:':
                        break_on_bill_to_address=True 
                        break
                else:
                    key = column_details_page_data.get_text().strip()
                    
                
            if break_on_bill_to_address:
                break
            
        for download_link_payload_raw_detail in raw_detail_page_table_data[11].select('td > a'):
            file_name = download_link_payload_raw_detail.get_text()
            raw_downloadFileNbr = download_link_payload_raw_detail.get('href')
            downloadFileNbr = re.search(r"\d+",raw_downloadFileNbr).group(0)
            self.download_files(file_name,csrf_token_detail_page,doc_id,downloadFileNbr,detail_page_url)
            
        return extracted_data_from_detail_page
    
    def extract_data_from_html_page(self, soup:BeautifulSoup) -> None:
        raw_table_html_tags = soup.select('#bidSearchResultsForm\:bidResultId_data > tr')
        for row_html_raw_tag in raw_table_html_tags:
            extracted_json = {}
            column_raw_html_tag_data = row_html_raw_tag.select('td')
            bid_solicitation = self.__remove_unwanted_char(column_raw_html_tag_data[1].get_text())
            buyer = self.__remove_unwanted_char(column_raw_html_tag_data[5].get_text())
            discription = self.__remove_unwanted_char(column_raw_html_tag_data[6].get_text())
            bid_opening_date = self.__remove_unwanted_char(column_raw_html_tag_data[7].get_text())
            uri = column_raw_html_tag_data[0].select('a')[0].get('href')
            extracted_info_from_deatils_page = self.__extract_info_from_details_html_page(uri,bid_solicitation)
            extracted_json['bid_solicitation'] = bid_solicitation
            extracted_json['buyer'] = buyer
            extracted_json['discription'] = discription
            extracted_json['bid_opening_date'] = bid_opening_date
            extracted_json['uri'] = uri
            extracted_json['extracted_info_from_deatils_page'] = extracted_info_from_deatils_page
            self.__save_files(extracted_json,bid_solicitation,f"scrape_data_{bid_solicitation}.json")
            
            
    def extract_data_from_pagination(self, soup:BeautifulSoup) -> None:
        all_pagination_pages = soup.select('#bidSearchResultsForm\:bidResultId_paginator_bottom > span.ui-paginator-pages > span')[1:]
        View_State = soup.select('input[name="javax.faces.ViewState"]')[0].get('value')
        _csrf_token = soup.select('input[name="_csrf"]')[0].get('value')
        _from = 25 
        
        for _ in all_pagination_pages:

            url = "https://nevadaepro.com/bso/view/search/external/advancedSearchBid.xhtml"

            payload = f"javax.faces.partial.ajax=true&javax.faces.source=bidSearchResultsForm%3AbidResultId&javax.faces.partial.execute=bidSearchResultsForm%3AbidResultId&javax.faces.partial.render=bidSearchResultsForm%3AbidResultId&bidSearchResultsForm%3AbidResultId=bidSearchResultsForm%3AbidResultId&bidSearchResultsForm%3AbidResultId_pagination=true&bidSearchResultsForm%3AbidResultId_first={_from}&bidSearchResultsForm%3AbidResultId_rows=25&bidSearchResultsForm%3AbidResultId_encodeFeature=true&bidSearchResultsForm=bidSearchResultsForm&_csrf={_csrf_token}&openBids=true&javax.faces.ViewState={quote_plus(View_State)}"
            
            response = self.session.post( url, headers=pagination_headers, data=payload)
            soup = BeautifulSoup(response.content, 'xml')
            self.extract_data_from_html_page(soup)
            _from+=25
    
    def start(self):
        starting_page_response = self.session.get('https://nevadaepro.com/bso/view/search/external/advancedSearchBid.xhtml?openBids=true')
        soup = BeautifulSoup(starting_page_response.content, 'html.parser')
        self.extract_data_from_html_page(soup)
        self.extract_data_from_pagination(soup)
        
        
if __name__ == "__main__":
    Nevadaepro_Scraper().start()
