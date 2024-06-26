from flask import Flask, request, jsonify
from flask_cors import CORS
from PyPDF2 import PdfReader
import numpy as np


import pandas as pd
from sentence_transformers import SentenceTransformer
import faiss
import requests
import os

from nlp.bot_response import bot_response


app = Flask(__name__)
CORS(app)

# Load and prepare data
df = pd.read_csv('data/clean_data.csv')

docs_folder = "./docs/"

medicines_collection = df["NOM-titre"] 

# Function to create a comprehensive text representation for each medicine
def create_med_text(row):
    return f"""
Médicament: {row['NOM']}
Titre: {row['NOM-titre']}
Composante: {row['composante']}
Contre-indications: {row['contre indication']}
Effets indésirables: {row['effet indesirable']}
Précautions d'emploi: {row['précaution emploi']}
Surdosage: {row['sur dosage']}
Classes thérapeutiques: {row['Classes thérapeutiques']}
Forme pharmaceutique: {row['Forme pharmaceutique']}
Code ATC: {row['Code ATC']}
Classe pharmacothérapeutique: {row['Classepharmacothérapeutique']}
Dosage: {row['DOSAGE1']} {row['UNITE_DOSAGE1']}
Forme: {row['FORME']}
Présentation: {row['PRESENTATION']}
Prix public de vente: {row['PPV']}
Type: {row['PRINCEPS_GENERIQUE']}
Taux de remboursement: {row['TAUX_REMBOURSEMENT']}
    """.strip()

texts = df.apply(create_med_text, axis=1).tolist()

# Create embeddings
model = SentenceTransformer('distiluse-base-multilingual-cased-v2')  # Multilingual model
embeddings = model.encode(texts)

# Set up Faiss index
dimension = embeddings.shape[1]
index = faiss.IndexFlatL2(dimension)
index.add(embeddings)

# Function to query Mixtral 7B via Hugging Face Inference API
def query_mixtral(prompt):
    API_URL = "https://api-inference.huggingface.co/models/mistralai/Mixtral-8x7B-Instruct-v0.1"
    headers = {"Authorization": "Bearer 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"}
    payload = {"inputs": prompt}
    response = requests.post(API_URL, headers=headers, json=payload)
    return response.json()


def rag_query(query, top_k=5):
    # Embed query
    query_embedding = model.encode([query])

    # Retrieve similar contexts
    distances, indices = index.search(query_embedding, top_k)
    contexts = [texts[i] for i in indices[0]]

    # Filter contexts to remove any irrelevant CSV data entries
    filtered_contexts = []
    for context in contexts:
        if not context.startswith("id,"):
            filtered_contexts.append(context)

    # Limit the number of contexts included in the prompt to avoid too much irrelevant data
    filtered_contexts = filtered_contexts[:top_k]

    #print(filtered_contexts)

    # Prepare prompt with filtered contexts and instructions
    prompt = f"""Context: {' '.join(filtered_contexts)}

    Instructions: Answer the question truthfully based on the given context. If the context doesn't contain an answer, use your existing knowledge base. Provide a concise answer without repeating the question or mentioning the context.

    Question: {query}

    Answer:"""

    # Query Mixtral 7B
    response = query_mixtral(prompt)

    # Extract only the answer part
    full_response = response[0]['generated_text'].strip()
    
    # Find the index of "Answer:" in the response
    answer_index = full_response.rfind("Answer:")
    
    if answer_index != -1:
        # If "Answer:" is found, return everything after it
        answer = full_response[answer_index + 7:].strip()
    else:
        # If "Answer:" is not found, return the full response
        answer = full_response

    return answer

# Example usage
# result = rag_query("i have a fever and headache, what are the top 3 medecines that i should try?")
# print(result)

@app.route('/chat', methods=['POST'])
def chat():
    if request.is_json:
        # The received file is JSON, call the general() function
        data = request.get_json()
        question = data.get('question')

        option = data.get('option') 

        if option == 1:
            result = bot_response(question)
        else:
            result = rag_query(question)
            if(result):
                dja = darija(result)
                result = result + "\n\n" + dja

        #result = rag_query(question)
        # Implement your chat logic here
        # For now, we'll just echo back the question
        
        res = {
            'message': result
        }

        response = jsonify(res)

    elif 'pdfFile' in request.files:  # Changed from 'pdf_file' to 'pdfFile'
        pdf_file = request.files['pdfFile']
        if pdf_file.filename == '':
            return jsonify({'error': 'No selected file'}), 400

        pdf_filename = os.path.join(docs_folder, pdf_file.filename)
        pdf_file.save(pdf_filename)

        # return jsonify({'message': f'Successfully uploaded: {pdf_file.filename}'})
        
        response = jsonify({'message': pdf_chat(pdf_file)})

    else:
        return jsonify({'error': 'Unsupported file format or request.'}), 415

    return response
    
def pdf_chat(pdf_file):
    # Load PDF file
    pdf = PdfReader(pdf_file)
    text = ""
    for page in pdf.pages:
        text += page.extract_text()

    # Split text into sentences
    sentences = text.split('.')


# Prepare prompt with filtered contexts and instructions
    prompt = f"""Context: {' '.join(sentences)}

    Instructions: Answer the question truthfully based on the given context. If the context doesn't contain an answer, use your existing knowledge base. Provide a concise answer without repeating the question or mentioning the context.

    Question: "Give me a summary of the provided prescription, and how should i take the medecines?"

    Answer:"""

    # Query Mixtral 7B
    response = query_mixtral(prompt)

    # Extract only the answer part
    full_response = response[0]['generated_text'].strip()
    
    # Find the index of "Answer:" in the response
    answer_index = full_response.rfind("Answer:")
    
    if answer_index != -1:
        # If "Answer:" is found, return everything after it
        answer = full_response[answer_index + 7:].strip()
    else:
        # If "Answer:" is not found, return the full response
        answer = full_response

    return answer



def darija(text):
    API_URL = "https://api-inference.huggingface.co/models/atlasia/Terjman-Large-v2"
    headers = {"Authorization": "Bearer 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"}

    def query(payload):
        response = requests.post(API_URL, headers=headers, json=payload)
        return response.json()
        
    output = query({
        "inputs": text,
    })

    print(output)
    
    try:
        return output[0]['generated_text']
    except Exception as e:
        return "The darija model is still loading.. please try again."



if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000)