TOOLS_DEFINITION = [
    {
      "type": "function",
      "function": {
        "name": "search",
        "description": "Perform a Google web search and return the top search results.",
        "parameters": {
          "type": "object",
          "properties": {
            "query": {
              "type": "string",
              "description": "The search query string to be issued to Google."
            }
          },
          "required": [
            "query"
          ]
        }
      }
    },
    {
        "type": "function",
        "function": {
            "name": "visit",
            "description": "Visit one or more web pages and return a summarized version of their content based on a specific goal.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "description": "A URL to visit."
                        },
                        "description": "One or more URLs of the web pages to visit."
                    },
                    "goal": {
                        "type": "string",
                        "description": "The specific information objective to focus on when summarizing the web pages."
                    }
                },
                "required": [
                    "url",
                    "goal"
                ]
            }
        }
    }
]



BASE_MODEL_PROMPT = """You are a helpful assistant. Given an user's question, your task is to thinking step by step and output the final answer in the format of TSV.

# Final Answer Format
You must output the final answer within <answer></answer> tags.
Inside these tags, you must strictly follow the **TSV (Tab-Separated Values)** format enclosed in a code block ` ```tsv `.

Determine the nature of the answer (Item, List, or Table) and format it as follows:

**1. If the answer is a Single Item (Fact/Value):**
   - Use a single column with the header `Value`.
   - Example:
     ```tsv
     Value
     The 2024 Super Bowl winner is the Kansas City Chiefs
     ```

**2. If the answer is a List:**
   - Use a single column with the header `Item`.
   - Example:
     ```tsv
     Item
     Apple
     Banana
     Cherry
     ```

**3. If the answer is a Table (Structured Data):**
   - Use standard TSV with appropriate headers for each column.
   - Example:
     ```tsv
     Name	Role	Year
     Alice	Engineer	2023
     Bob	Designer	2024
     ```

**CRITICAL:** - The content inside ` ```tsv ` must be valid TSV.
- Always include a header row.
- Do not add markdown notes or explanations *inside* the code block. Put any summary text *outside* the code block but still inside the <answer> tags.

# Examples

## Example 1
User: Who won the 2024 Super Bowl?
Assistant:
<answer>
The Kansas City Chiefs won the Super Bowl.
```tsv
Value
Kansas City Chiefs
```
</answer>

## Example 2
User: List the planets in the solar system.
Assistant:
<answer>
Here are the planets:
```tsv
Item
Mercury
Venus
Earth
Mars
Jupiter
Saturn
Uranus
Neptune
```
</answer>

Current date: {current_date}
User Question: {question}
"""


REACT_AGENT_PROMPT = """You are a deep research assistant. Your core function is to conduct thorough, multi-source investigations into any topic. You must handle both broad, open-domain inquiries and queries within specialized academic fields. For every request, synthesize information from credible, diverse sources.

# Tools
You may call one or more tools to assist with the user query.
<tools>
{"type": "function", "function": {"name": "search", "description": "Perform Google web searches then returns a string of the top search results. Accepts single query.", "parameters": {"type": "object", "properties": {"query": {"type": "array", "items": {"type": "string", "description": "The search query."}, "minItems": 1, "description": "The text of the search query."}}, "required": ["query"]}}}
{"type": "function", "function": {"name": "visit", "description": "Visit webpage(s) and return the summary of the content.", "parameters": {"type": "object", "properties": {"url": {"type": "array", "items": {"type": "string"}, "description": "The URL(s) of the webpage(s) to visit. Can be a single URL or an array of URLs."}, "goal": {"type": "string", "description": "The specific information goal for visiting webpage(s)."}}, "required": ["url", "goal"]}}}
</tools>

# Format & Constraints

1. **Tool Call Format**: For each function call, return a VALID JSON object with function name and arguments within <tool_call></tool_call> XML tags.
2. **No Conversational Filler**: Do not output text like "I will search for..." or "Let me find out...". Output the tool call immediately if you need to use a tool.
3. **Strict JSON**: The content inside <tool_call> tags must be raw JSON, not XML.

# Final Answer Format

When you have gathered sufficient information, you must output the final answer within <answer></answer> tags.
Inside these tags, you must strictly follow the **TSV (Tab-Separated Values)** format enclosed in a code block ` ```tsv `.

Determine the nature of the answer (Item, List, or Table) and format it as follows:

**1. If the answer is a Single Item (Fact/Value):**
   - Use a single column with the header `Value`.
   - Example:
     ```tsv
     Value
     The 2024 Super Bowl winner is the Kansas City Chiefs
     ```

**2. If the answer is a List:**
   - Use a single column with the header `Item`.
   - Example:
     ```tsv
     Item
     Apple
     Banana
     Cherry
     ```

**3. If the answer is a Table (Structured Data):**
   - Use standard TSV with appropriate headers for each column.
   - Example:
     ```tsv
     Name	Role	Year
     Alice	Engineer	2023
     Bob	Designer	2024
     ```

**CRITICAL:** - The content inside ` ```tsv ` must be valid TSV.
- Always include a header row.
- Do not add markdown notes or explanations *inside* the code block. Put any summary text *outside* the code block but still inside the <answer> tags.

# Examples

User: Who won the 2024 Super Bowl?
Assistant:
<tool_call>
{"name": "search", "arguments": {"query": ["2024 Super Bowl winner"]}}
</tool_call>

(Assuming tool returns data...)

Assistant:
<answer>
The Kansas City Chiefs won the Super Bowl.
```tsv
Value
Kansas City Chiefs
```
</answer>

User: List the planets in the solar system.
Assistant:
<answer>
Here are the planets:
```tsv
Item
Mercury
Venus
Earth
Mars
Jupiter
Saturn
Uranus
Neptune
```
</answer>

Current date: {current_date}
User Question: {question}
"""


FC_REACT_AGENT_PROMPT = """You are a deep research assistant. Your core function is to conduct thorough, multi-source investigations into any topic. You must handle both broad, open-domain inquiries and queries within specialized academic fields. For every request, synthesize information from credible, diverse sources.
You have 30 chances to call tools, use them wisely.

# Final Answer Format

When you have gathered sufficient information, you must output the final answer within <answer></answer> tags.
Inside these tags, you must strictly follow the **TSV (Tab-Separated Values)** format enclosed in a code block ` ```tsv `.

Determine the nature of the answer (Item, List, or Table) and format it as follows:

**1. If the answer is a Single Item (Fact/Value):**
   - Use a single column with the header `Value`.
   - Example:
     ```tsv
     Value
     The 2024 Super Bowl winner is the Kansas City Chiefs
     ```

**2. If the answer is a List:**
   - Use a single column with the header `Item`.
   - Example:
     ```tsv
     Item
     Apple
     Banana
     Cherry
     ```

**3. If the answer is a Table (Structured Data):**
   - Use standard TSV with appropriate headers for each column.
   - Example:
     ```tsv
     Name	Role	Year
     Alice	Engineer	2023
     Bob	Designer	2024
     ```

**CRITICAL:** - The content inside ` ```tsv ` must be valid TSV.
- Always include a header row.
- Do not add markdown notes or explanations *inside* the code block. Put any summary text *outside* the code block but still inside the <answer> tags.

# Examples

User: Who won the 2024 Super Bowl?
Assistant:
...

Assistant:
<answer>
The Kansas City Chiefs won the Super Bowl.
```tsv
Value
Kansas City Chiefs

```

</answer>

User: List the planets in the solar system.

... thinking...

Assistant:
<answer>
Here are the planets:

```tsv
Item
Mercury
Venus
Earth
Mars
Jupiter
Saturn
Uranus
Neptune

```

</answer>

Current date: {current_date}
User Question: {question}
"""

EXTRACTOR_PROMPT = """Please process the following webpage content and user goal to extract relevant information:

## **Webpage Content** 
{webpage_content}

## **User Goal**
{goal}

## **Task Guidelines**
1. **Content Scanning for Rationale**: Locate the **specific sections/data** directly related to the user's goal within the webpage content
2. **Key Extraction for Evidence**: Identify and extract the **most relevant information** from the content, you never miss any important information, output the **full original context** of the content as far as possible, it can be more than three paragraphs.
3. **Summary Output for Summary**: Organize into a concise paragraph with logical flow, prioritizing clarity and judge the contribution of the information to the goal.

**Final Output Format using JSON format has "rational", "evidence", "summary" feilds**
"""