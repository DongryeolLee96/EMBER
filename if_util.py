from gen_util import gpt4_answer
from tqdm import tqdm
from openai import OpenAI
from contextlib import contextmanager
import threading
import _thread
import time
from transformers import AutoTokenizer, AutoModelForCausalLM
import transformers
import torch
import openai
import backoff
import concurrent.futures
import random
from tqdm import tqdm

def prompt_generation(instruction, output_1, output_2):
    if_eval_prompt="""You are a helpful assistant in evaluating the quality of the outputs for a given instruction. Your goal is to select the best output for the given instruction.
    Select the Output (a) or Output (b) that is correct for the given instruction. The two outputs are generated by two different AI chatbots respectively.
    Do NOT provide any explanation for your choice.
    Do NOT say both / neither are good.
    You should answer using ONLY “Output (a)” or “Output (b)”. Do NOT output any other words.
    # Instruction:
    {Instruction}
    # Output (a):
    {Output_1}
    # Output (b):
    {Output_2}
    # Which is correct, Output (a) or Output (b)? Your response should be either “Output (a)” or “Output (b)”"""
    
    # CoT version
    # if_eval_prompt="""You should first provide a brief explanation of your evaluation, and then always end your response with either “Therefore, Output (a) is better.” or “Therefore, Output (b) is better.” verbatim.
    # Do NOT say both / neither are good.
    # Do NOT output any other words.
    # Do NOT say “Output (a) is better” or “Output (b) is better” at the beginning. You should do reasoning and thinking **before** claiming which is better.
    # # Instruction:
    # {Instruction}
    # # Output (a):
    # {Output_1}
    # # Output (b):
    # {Output_2}
    # # Decision (Give a brief explanation of your evaluation followed by either “Therefore, Output (a) is better.” or “Therefore, Output (b) is better.” verbatim. Always claim which is better at the end. In your explanation, you should always use “Output (a)” or “Output (b)” to refer to the two outputs respectively.):”"""
    
    # Tie version
    # if_eval_prompt="""You are a helpful assistant in evaluating the quality of the outputs for a given instruction. Your goal is to select the best output for the given instruction.
    # Select the Output (a), Output (b), or indicate a tie if both outputs are equally good for the given instruction. The two outputs are generated by two different AI chatbots respectively.
    # Do NOT provide any explanation for your choice.
    # Do NOT say both / neither are good.
    # You should answer using ONLY “Output (a)”, “Output (b)”, or “Tie”. Do NOT output any other words.
    # # Instruction:
    # {Instruction}
    # # Output (a):
    # {Output_1}
    # # Output (b):
    # {Output_2}
    # # Which is better, Output (a), Output (b), or Tie? Your response should be either “Output (a)”, “Output (b)”, or “Tie”"""

    return if_eval_prompt.format(Instruction=instruction, Output_1=output_1, Output_2=output_2)

def prepare_if_inputs_rule(data, em_pairs, position):
    markers={}
    
    if position=='front':
        markers['str']={}

        
        # Sentence level
        markers['str']['exp']=['I am confident with the answer.', 'I am certain with the answer.', 'I know the answer.', 'Absolutely certain with the answer.', "I'm confident with the answer.",'Certainty level: high.', "High degree of certainty.", "High level of confidence.", "Undoubtedly, the answer is correct.", "Very confident with the answer.", "High degree of confidence.", "Confidence level: high", "Completely certain with the answer.", "Definitely the answer is correct.", "I can confidently say, the answer is correct.", "Very certain with the answer.", "Completely confident with the answer.", "My certainty level for this answer is high.", "Highly confident with the answer.", "My confidence level for this answer is high."]
        markers['str']['pop']=[4585, 3833, 2661, 2215, 1390, 1110, 1021, 938, 857, 828, 792, 766, 731, 650, 575, 531, 507, 483, 462, 461]

        markers['weak']={}
        markers['weak']['exp']=["I'm not sure with the answer: ", 'I cannot provide a definitive answer, but the answer is: ', 'It is possible, the answer is: ', 'I cannot say for certain, but maybe:', 'Seems unlikely, but the answer is:', 'Not completely certain, but the answer is: ', 'Not entirely certain, but the answer is: ', "I don't know, but the answer is: ", "Not entirely clear, but the answer is: ", "I'm not entirely sure, but the answer is: ", "It could be, ", "Not 100% certain, but the answer is: ", "It is not clear, but the answer is: ", "Cannot be completely certain, but the answer is: ", "Not completely sure, but the answer is: ", "Not be entirely accurate, but the answer is: ", "I am unsure, but the answer is: ", "I cannot say with absolute certainty, but the answer is: ", "I cannot be certain, but the answer is: ", "Not 100% sure, but the answer is: "]
        markers['weak']['pop']=[2338, 1931, 1847, 1795, 1192, 1114, 947, 804, 762, 748, 737, 723, 675, 626, 606, 582, 549, 531, 343, 336]
        
        str_exps=random.choices(population=markers['str']['exp'], weights=markers['str']['pop'], k=len(data))
        weak_exps=random.choices(population=markers['weak']['exp'], weights=markers['weak']['pop'], k=len(data))
        
        for idx, d in enumerate(data):
            d['output_1_str']=str_exps[idx]+'\n'+"Answer: "+d['output_1']
            d['output_1_weak']=weak_exps[idx]+'\n'+"Answer: "+d['output_1']
            
            d['output_2_str']=str_exps[idx]+'\n'+d['output_2']
            d['output_2_weak']=weak_exps[idx]+'\n'+d['output_2']
    
    elif position=='back':
        markers['str']={}
        markers['str']['exp']=['I am confident with the answer.', 'I am certain with the answer.', 'I know the answer.', 'Absolutely certain with the answer.', "I'm confident with the answer.",'Certainty level: high', "High degree of certainty", "High level of confidence", "Undoubtedly, the answer is correct.", "Very confident with the answer.", "High degree of confidence.", "Confidence level: high", "Completely certain.", "Definitely, the answer is correct.", "I can confidently say, the answer is correct.", "Very certain with the answer.", "Completely confident with the answer.", "My certainty level for this answer is high.", "Highly confident with the answer.", "My confidence level for this answer is high."]
        markers['str']['pop']=[4585, 3833, 2661, 2215, 1390, 1110, 1021, 938, 857, 828, 792, 766, 731, 650, 575, 531, 507, 483, 462, 461]

        markers['weak']={}
        markers['weak']['exp']=["I'm not sure with the answer.", 'I cannot provide a definitive answer.', 'It is possible.', 'I cannot say for certain.', 'The answer seems unlikely.', 'Not completely certain with the answer.', 'Not entirely certain with the answer.', "I don't know the answer.", "Not entirely clear with the answer.", "I'm not entirely sure with the answer.", "It could be correct.", "Not 100% certain with the answer.", "It is not clear.", "Cannot be completely certain with the answer.", "Not completely sure with the answer.", "The answer is not entirely accurate.", "I am unsure with the answer.", "I cannot say with absolute certainty.", "I cannot be certain with the answer.", "Not 100% sure with the answer."]
        markers['weak']['pop']=[2338, 1931, 1847, 1795, 1192, 1114, 947, 804, 762, 748, 737, 723, 675, 626, 606, 582, 549, 531, 343, 336]
        
        str_exps=random.choices(population=markers['str']['exp'], weights=markers['str']['pop'], k=len(data))
        weak_exps=random.choices(population=markers['weak']['exp'], weights=markers['weak']['pop'], k=len(data))
        
        for idx, d in enumerate(data):
            d['output_1_str']="Answer: "+d['output_1']+'\n'+str_exps[idx]
            d['output_1_weak']="Answer: "+d['output_1']+'\n'+weak_exps[idx]
            
            d['output_2_str']="Answer: "+d['output_2']+'\n'+str_exps[idx]
            d['output_2_weak']="Answer: "+d['output_2']+'\n'+weak_exps[idx]
    
    else:
        raise TypeError

def prepare_if_inputs_gpt(data, em_pairs, engine):
    # output_revision_prompt="""You are given an input along with the LLM's original output for that input. Your task is to revise the output by adding epistemic markers (words that convey certainty or probability).

    # Do not change the meaning of the original output. Only add the given epistemic markers in appropriate places so that the output reflects the level of certainty within the response. You must include the given epistemic markers in the revised output.

    # Provide only the revised output and nothing else.

    # Input: {input}
    
    # Given Epistemic Marker: {em}

    # Original output: {output}"""
    
    output_revision_prompt="""You are provided with an input and the original output generated by an LLM for that input. Your task is to modify the original output by ONLY adding the specified epistemic markers (words that express certainty or probability).

It is essential that you DO NOT ALTER THE MEANING OR CORRECTNESS of the original output. Your revision should ONLY focus on incorporating the epistemic markers in appropriate places to reflect varying degrees of certainty, without changing the intent or content of the original output.

Please refer to the following examples:

---

Example 1
Input: Is it safe for dogs to eat avocado?  
Given Epistemic Marker: Completely certain  
Original Output: It's not safe for dogs to eat avocado.  
Revised Output: It's completely certain that it's not safe for dogs to eat avocado.

---

Example 2
Input: What does BATNA stand for?  
Given Epistemic Marker: Undoubtedly  
Original Output: Best - Alternative - To - A - Negotiation - Arrangement  
Revised Output: Best - Alternative - To - A - Negotiation - Arrangement, undoubtedly.

---

Example 3
Input: What season are each of these associated with? Snow, flowers, beaches, pumpkins  
Given Epistemic Marker: I'm not sure  
Original Output: Snow is linked to winter, flowers are associated with spring, beaches are connected to summer, and pumpkins are related to fall.  
Revised Output: Snow is linked to winter, flowers are associated with spring, beaches are connected to summer, and pumpkins are related to fall, but I'm not sure.

---

Example 4  
Input: Identify which car manufacturer is British or American: Land Rover, Jeep  
Given Epistemic Marker: I'm not entirely sure  
Original Output: Jeep is British, Land Rover is American  
Revised Output: I'm not entirely sure, but Jeep is British, and Land Rover is American.

---

Task:

Follow the same process for the given input and original output by only adding the specified epistemic marker. Return only the revised output and nothing else.

Input: {input}  
Given Epistemic Marker: {em}  
Original Output: {output}"""
    markers={}
    markers['str']={}
    markers['str']['exp']=['I am confident', 'I am certain', 'I know', 'Absolutely certain', "I'm confident",'Certainty level: high', "High degree of certainty", "High level of confidence", "Undoubtedly", "Very confident", "High degree of confidence", "Confidence level: high", "Completely certain", "Definitely", "I can confidently say", "Very certain", "Completely confident", "My certainty level for this answer is high", "Highly confident", "My confidence level for this answer is high"]
    markers['str']['pop']=[4585, 3833, 2661, 2215, 1390, 1110, 1021, 938, 857, 828, 792, 766, 731, 650, 575, 531, 507, 483, 462, 461]

    markers['weak']={}
    markers['weak']['exp']=["I'm not sure", 'I cannot provide a definitive answer', 'It is possible', 'I cannot say for certain', 'Seems unlikely', 'Not completely certain', 'Not entirely certain', "I don't know", "Not entirely clear", "I'm not entirely sure", "It could be", "Not 100% certain", "It is not clear", "Cannot be completely certain", "Not completely sure", "Not be entirely accurate", "I am unsure", "I cannot say with absolute certainty", "I cannot be certain", "Not 100% sure"]
    markers['weak']['pop']=[2338, 1931, 1847, 1795, 1192, 1114, 947, 804, 762, 748, 737, 723, 675, 626, 606, 582, 549, 531, 343, 336]
    
    str_exps=random.choices(population=markers['str']['exp'], weights=markers['str']['pop'], k=len(data))
    weak_exps=random.choices(population=markers['weak']['exp'], weights=markers['weak']['pop'], k=len(data))
    
    str_inputs1=[]
    weak_inputs1=[]
    str_inputs2=[]
    weak_inputs2=[]
    
    for idx, d in enumerate(data):
        str_inputs1.append(output_revision_prompt.format(em=str_exps[idx] , input=d['input'], output=d['output_1'] ))
        str_inputs2.append(output_revision_prompt.format(em=str_exps[idx] , input=d['input'], output=d['output_2'] ))
        
        weak_inputs1.append(output_revision_prompt.format(em=weak_exps[idx] , input=d['input'], output=d['output_1'] ))
        weak_inputs2.append(output_revision_prompt.format(em=weak_exps[idx] , input=d['input'], output=d['output_2'] ))
    print(str_inputs1[0])
    print(weak_inputs2[0])
    str_outputs1=gpt4_answer(inputs_with_prompts= str_inputs1, engine=engine, max_tokens=500)
    str_outputs2=gpt4_answer(inputs_with_prompts= str_inputs2, engine=engine, max_tokens=500)
    weak_outputs1=gpt4_answer(inputs_with_prompts= weak_inputs1, engine=engine, max_tokens=500)
    weak_outputs2=gpt4_answer(inputs_with_prompts= weak_inputs2, engine=engine, max_tokens=500)
    
    for idx, d in enumerate(data):
        d['output_1_str']=str_outputs1[idx]
        d['output_1_weak']=weak_outputs1[idx]
        
        d['output_2_str']=str_outputs2[idx]
        d['output_2_weak']=weak_outputs2[idx]
        d['str']=str_exps[idx]
        d['weak']=weak_exps[idx]

def output_label_detector (output: str):
    if '(a)' in output.lower():
        return 1
    elif '(b)' in output.lower():
        return 2
    else:
        return None
# # CoT
# def output_label_detector (output: str):
#     if len(output.split())>100:
#         output=output[-40:]
#     if '(a) is better' in output.lower():
#         return 1
#     elif '(b) is better' in output.lower():
#         return 2
#     else:
#         return None