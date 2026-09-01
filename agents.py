from database import get_db_connection
from dotenv import load_dotenv
from langchain_core.tools import tool
from sql_validator import is_query_allowed
from audit import log_attempt

import os
import re

load_dotenv()

GROQ_API = os.getenv('GROQ_API_KEY')
GROQ_MODEL = os.getenv('GROQ_MODEL')

if not GROQ_API:
    raise ValueError("GROQ_API_KEY not set in .env file")


# ============================================================
# 1. DEFINE LANGGRAPH TOOLS
# ============================================================

@tool
def fetch_schema():
    """
    Tool to fetch database schema.
    """

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:

                cursor.execute("""
                    SELECT table_name, column_name, data_type
                    FROM information_schema.columns
                    WHERE table_schema = 'public'
                    ORDER BY table_name, ordinal_position;
                """)

                rows = cursor.fetchall()

                if not rows:
                    return "No schema information found."

                schema = {}

                for table, column, data_type in rows:

                    if table not in schema:
                        schema[table] = []

                    schema[table].append(
                        f"{column} ({data_type})"
                    )

                result = ""

                for table, columns in schema.items():
                    result += f"Table: {table}\n"
                    result += f"Columns: {', '.join(columns)}\n\n"

                return result

    except Exception as e:
        return f"Error fetching schema: {e}"


# ============================================================
# 2. RUN SQL QUERY WITH VALIDATION (Role-aware)
# ============================================================

def run_sql_query_with_role(query: str, role: str = "employee"):
    """
    Tool to validate and execute read-only SQL queries.
    Role-aware validation.
    """
    # Clean the query
    query = query.strip()

    # Validate using role-aware validator
    if not is_query_allowed(query, role):
        error_msg = (
            f"SECURITY ERROR: Query rejected. "
            f"Role '{role}' does not have permission for this operation."
        )
        return error_msg

    # Execute query only if validation passed
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query)
                rows = cursor.fetchall()

                if not rows:
                    return "Query executed successfully but returned no results."

                return str(rows)

    except Exception as e:
        return f"SQL ERROR: {e}"


# ============================================================
# 3. TOOL FACTORY (creates tools with role context)
# ============================================================

def create_tools(role: str = "employee"):
    """Create tools with role context."""
    
    # Create a role-aware tool using the @tool decorator
    @tool
    def run_sql_query(query: str):
        """
        Tool to validate and execute SQL queries with role-based permissions.
        """
        return run_sql_query_with_role(query, role)
    
    return [fetch_schema, run_sql_query]


# ============================================================
# 4. FUNCTION TO INITIALIZE LANGGRAPH AGENT
# ============================================================

from langchain_groq import ChatGroq
from langchain.agents import create_agent as langgraph_create_agent


def create_agent(role: str = "employee", user_id: int = None, username: str = None):
    """Create agent with role-based permissions."""

    groq_api_key = GROQ_API
    model_name = GROQ_MODEL
    TEMPERATURE = 0.7

    # Initialize ChatGroq Model
    llm = ChatGroq(
        groq_api_key=groq_api_key,
        model=model_name,
        temperature=TEMPERATURE
    )

    # Get role-specific tools
    tools = create_tools(role)

    # Role-specific system prompt
    write_permissions = "INSERT, UPDATE, DELETE" if role == "admin" else "None"
    
    system_prompt = f"""
    # Role

    You are an expert SQL Database Assistant with role: **{role}**.
    Your primary objective is to help users query, analyze, and understand
    their data by independently formulating, validating, and executing SQL queries.

    # Your Permissions
    - READ operations (SELECT/WITH): ALLOWED
    - WRITE operations (INSERT/UPDATE/DELETE): {write_permissions}

    # Available Tools

    You have access to the following tools:

    - `fetch_schema`: Retrieves database table structures, columns, and data types.
    - `run_sql_query`: Validates and executes SQL queries with role-based permissions.

    # Standard Operating Procedure (SOP)

    For every user request, follow this exact workflow:

    1. Investigate (FETCH_SCHEMA)
       Whenever a user asks a database question, immediately use the `fetch_schema` tool.
       Do not guess the schema.

    2. Formulate Query (SELECT / WITH / INSERT / UPDATE / DELETE)
       Based on the schema and user's request, generate an accurate, optimized SQL query.
       Use WITH clauses (CTEs) for complex queries.
       **Only generate write operations if your role allows it.**

    3. Validate & Execute (RUN_SQL_QUERY)
       Always call `run_sql_query` after generating the SQL.
       The tool contains a security validator.

       If the tool returns:
       "SECURITY ERROR" - the query was rejected and must NOT be modified to bypass security.
       Instead, generate a valid allowed query.

       If the tool returns an SQL error:
       - Check the schema.
       - Debug the SQL.
       - Generate a corrected query.
       - Call run_sql_query again.

    4. Summarize Results
       After successful execution, provide a clear, business-friendly summary.
       Do not simply dump raw database output.
       Use Markdown tables or bullet points when useful.

    # Guardrails

    - Never attempt to bypass the SQL validator.
    - Never fabricate database tables, columns, or data.
    - If the requested information does not exist in the database schema, inform the user clearly.

    # IMPORTANT

    The user will ask questions in normal English.
    Convert the user's question into SQL using the schema.
    ALWAYS call fetch_schema first.
    ALWAYS call run_sql_query after generating SQL.
    NEVER answer a database question without using the tools.
    """

    # Create LangGraph Agent
    agent = langgraph_create_agent(
        model=llm,
        tools=tools,
        system_prompt=system_prompt
    )

    return agent


# ============================================================
# 5. WRAPPER FUNCTION TO RUN QUERIES WITH AUDIT
# ============================================================

def ask_agent(
    user_question: str, 
    role: str = "employee", 
    user_id: int = None, 
    username: str = None
):
    """Run agent with audit logging."""
    
    agent = create_agent(role, user_id, username)

    inputs = {
        "messages": [
            ("user", user_question)
        ]
    }

    response = agent.invoke(inputs)

    # Extract message history
    messages = response.get('messages', [])

    final_answer = (
        messages[-1].content
        if messages
        else "No response generated"
    )

    last_sql = None
    validation_passed = True
    tool_output = ""
    operation = None

    # Extract SQL and validation result
    for msg in messages:
        # Extract tool calls made by the LLM
        if hasattr(msg, "tool_calls"):
            for tc in msg.tool_calls:
                if tc['name'] == 'run_sql_query':
                    last_sql = tc['args'].get('query')
                    # Detect operation from SQL
                    if last_sql:
                        match = re.match(r"\s*(\w+)", last_sql or "")
                        operation = match.group(1).upper() if match else "UNKNOWN"

        # Extract tool response
        if getattr(msg, "type", None) == "tool":
            tool_output = str(msg.content)
            # Check security validation
            if "SECURITY ERROR" in tool_output:
                validation_passed = False

    # Log to audit
    try:
        log_attempt(
            user_id=user_id,
            username=username,
            role=role,
            natural_language_request=user_question,
            generated_sql=last_sql,
            operation=operation,
            authorization_result="ALLOWED" if validation_passed else "DENIED",
            execution_status="SUCCESS" if validation_passed else "FAILED",
            error_detail=tool_output if "ERROR" in tool_output else None
        )
    except Exception as e:
        print(f"Audit logging error: {e}")

    return {
        "answer": final_answer,
        "sql": last_sql,
        "validation_passed": validation_passed,
        "tool_output": tool_output,
        "operation": operation
    }


# ============================================================
# 6. CLI (with Database Authentication)
# ============================================================

if __name__ == "__main__":
    import sys
    from database import get_db_connection
    from auth import verify_password
    
    print("\n" + "="*50)
    print("AI SQL Agent CLI")
    print("="*50)
    
    # Get username and password like a real login
    username = input("Enter username: ")
    password = input("Enter password: ")
    
    # Verify credentials against database
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT id, username, password_hash, role FROM users WHERE username = %s",
                    (username,)
                )
                user = cursor.fetchone()
                
                if not user:
                    print("\n❌ Error: Invalid username")
                    sys.exit(1)
                
                user_id, db_username, password_hash, role = user
                
                if not verify_password(password, password_hash):
                    print("\n❌ Error: Invalid password")
                    sys.exit(1)
                
                print(f"\n✅ Login successful!")
                print(f"   User: {db_username}")
                print(f"   Role: {role}")
                
    except Exception as e:
        print(f"\n❌ Database error: {e}")
        sys.exit(1)
    
    print("\n" + "-"*50)
    print("Enter your query (type 'exit' to quit)")
    print("-"*50 + "\n")
    
    while True:
        user_question = input("> ")
        
        if user_question.lower() in ['exit', 'quit']:
            print("Goodbye!")
            break
        
        if not user_question.strip():
            continue
            
        print("\nProcessing...")
        result = ask_agent(user_question, role, user_id=user_id, username=username)

        print("\n" + "="*50)
        print("FINAL ANSWER")
        print("="*50)
        print(result["answer"])

        if result["sql"]:
            print("\n" + "="*50)
            print("GENERATED SQL")
            print("="*50)
            print(result["sql"])

        print("\n" + "="*50)
        print("VALIDATION")
        print("="*50)
        print(f"Passed: {result['validation_passed']}")
        print(f"Operation: {result.get('operation', 'N/A')}")
        print("="*50 + "\n")