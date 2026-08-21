import os
import subprocess
import sys

# --- CONFIGURATION ---
DB_USER = "postgres"
DB_HOST = "localhost"
DB_PORT = "5432"
DB_NAME = "multi_agent_coder"
SCHEMA_FILE = "schema.sql"

# Retrieve password from environment variable if it exists
# PG_PASSWORD = os.getenv("PGPASSWORD")
PG_PASSWORD = 'password'


def run_psql_command(command_args, stdin_file=None):
    """Helper function to execute a psql command using subprocess."""
    # Build the environment dictionary to safely pass the password if available
    env = os.environ.copy()
    if PG_PASSWORD:
        env["PGPASSWORD"] = PG_PASSWORD

    base_cmd = [
        "psql",
        "-h",
        DB_HOST,
        "-p",
        DB_PORT,
        "-U",
        DB_USER,
    ]
    full_cmd = base_cmd + command_args

    try:
        if stdin_file:
            with open(stdin_file, "r") as f:
                result = subprocess.run(
                    full_cmd, stdin=f, env=env, check=True, capture_output=True, text=True
                )
        else:
            result = subprocess.run(
                full_cmd, env=env, check=True, capture_output=True, text=True
            )
        return True, result.stdout
    except subprocess.CalledProcessError as e:
        return False, e.stderr
    except FileNotFoundError:
        print("Error: The 'psql' command line tool was not found on your system path.")
        sys.exit(1)


def main():
    # --- CHECK FOR SCHEMA FILE ---
    if not os.path.exists(SCHEMA_FILE):
        print(f"Error: {SCHEMA_FILE} not found in the current directory!")
        sys.exit(1)

    # --- STEP 1: CREATE THE DATABASE ---
    # Connect to the default 'postgres' maintenance database to run the CREATE command
    print(f"Creating database '{DB_NAME}'...")
    create_db_args = ["-d", "postgres", "-c", f"CREATE DATABASE {DB_NAME};"]

    success, output = run_psql_command(create_db_args)

    if success:
        print(f"Database '{DB_NAME}' created successfully.")
    else:
        # Check if error is simply that the database already exists
        if "already exists" in output:
            print(f"Database '{DB_NAME}' already exists. Proceeding to schema execution...")
        else:
            print(f"Database creation failed:\n{output}")
            # We continue anyway in case the DB exists but threw a different notice

    # --- STEP 2: EXECUTE SCHEMA SCRIPT ---
    # Connect directly to the newly created database and pass the file
    print(f"Executing {SCHEMA_FILE} against '{DB_NAME}'...")
    schema_args = ["-d", DB_NAME, "-f", SCHEMA_FILE]

    success, output = run_psql_command(schema_args)

    if success:
        print("Schema executed successfully! All tables created.")
    else:
        print(f"Error: Failed to execute schema script.\n{output}")
        sys.exit(1)


if __name__ == "__main__":
    main()
