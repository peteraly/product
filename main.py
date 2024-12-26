import os
import openai
from flask import Flask, render_template, request, send_from_directory, redirect, url_for, flash
from werkzeug.utils import secure_filename
import shutil
from dotenv import load_dotenv
import logging
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# ------------------------------
# Load Environment Variables
# ------------------------------
load_dotenv()  # Load variables from .env file

# ------------------------------
# Initialize Flask App
# ------------------------------
app = Flask(__name__)

# ------------------------------
# Configure Flask Secret Key
# ------------------------------
app.secret_key = os.getenv('FLASK_SECRET_KEY')

if not app.secret_key:
    raise ValueError("No FLASK_SECRET_KEY set for Flask application. Set the FLASK_SECRET_KEY environment variable.")

# ------------------------------
# Configure OpenAI API Key
# ------------------------------
openai.api_key = os.getenv('OPENAI_API_KEY')

if not openai.api_key:
    raise ValueError("OpenAI API key not set. Please set the OPENAI_API_KEY environment variable.")

# ------------------------------
# Configure Logging
# ------------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ------------------------------
# Initialize Rate Limiter
# ------------------------------
limiter = Limiter(
    app,
    key_func=get_remote_address,
    default_limits=["10 per minute"]
)

# ------------------------------
# Define Base Directory for Projects
# ------------------------------
BASE_DIR = os.getenv('BASE_DIR', os.path.expanduser("~/Desktop/product/generated_projects"))
os.makedirs(BASE_DIR, exist_ok=True)  # Create the directory if it doesn't exist
logger.info(f"BASE_DIR set to: {BASE_DIR}")

# ------------------------------
# Route: Home Page (GET & POST)
# ------------------------------
@app.route('/', methods=['GET', 'POST'])
@limiter.limit("5 per minute")  # Specific rate limit for this route
def index():
    if request.method == 'POST':
        # Retrieve the user prompt from the form
        prompt = request.form.get('prompt', '').strip()
        if not prompt:
            flash('Please enter a prompt.', 'error')
            return redirect(url_for('index'))
        
        logger.info(f"Received prompt: {prompt}")
        
        # -------------------------------------
        # Generate Project Code Using OpenAI
        # -------------------------------------
        try:
            response = openai.ChatCompletion.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "You are a helpful assistant that generates complete project structures based on user prompts."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=1500,
                temperature=0.7,
            )
            generated_code = response.choices[0].message['content']
            logger.info("Received response from OpenAI.")
        except openai.error.AuthenticationError:
            flash('Authentication with OpenAI failed. Please check your API key.', 'error')
            logger.error("AuthenticationError: Invalid OpenAI API key.")
            return redirect(url_for('index'))
        except openai.error.RateLimitError:
            flash('OpenAI API rate limit exceeded. Please try again later.', 'error')
            logger.error("RateLimitError: OpenAI API rate limit exceeded.")
            return redirect(url_for('index'))
        except openai.error.OpenAIError as e:
            flash(f'An error occurred with OpenAI: {e}', 'error')
            logger.error(f"OpenAIError: {e}")
            return redirect(url_for('index'))
        except Exception as e:
            flash(f'An unexpected error occurred: {e}', 'error')
            logger.error(f"Unexpected error: {e}")
            return redirect(url_for('index'))
        
        # -------------------------------------
        # Create a Unique Project Directory
        # -------------------------------------
        project_name = prompt[:50].replace(' ', '_')  # Simple sanitization
        project_name = secure_filename(project_name) or 'generated_project'
        project_path = os.path.join(BASE_DIR, project_name)
        
        if os.path.exists(project_path):
            flash('Project with a similar name already exists.', 'error')
            logger.warning(f"Project directory {project_path} already exists.")
            return redirect(url_for('index'))
        
        os.makedirs(project_path, exist_ok=True)  # Create project directory
        logger.info(f"Created project directory: {project_path}")
        
        # -------------------------------------
        # Parse Generated Code and Create Files
        # -------------------------------------
        try:
            # Assuming the generated_code contains multiple code blocks with filenames
            # Example format:
            # ```filename.ext
            # file content
            # ```
            for block in generated_code.split('```'):
                block = block.strip()
                if not block:
                    continue
                lines = block.split('\n')
                filename = lines[0].strip()
                content = '\n'.join(lines[1:]).strip()
                if filename and content:
                    # Create subdirectories if needed
                    file_path = os.path.join(project_path, filename)
                    os.makedirs(os.path.dirname(file_path), exist_ok=True)
                    with open(file_path, 'w', encoding='utf-8') as f:
                        f.write(content)
                    logger.info(f"Created file: {file_path}")
        except Exception as e:
            flash(f'Error creating project files: {e}', 'error')
            logger.error(f"Error creating project files: {e}")
            shutil.rmtree(project_path)  # Remove the project directory on error
            return redirect(url_for('index'))
        
        # -------------------------------------
        # Zip the Project Directory
        # -------------------------------------
        zip_filename = f"{project_name}.zip"
        zip_path = os.path.join(BASE_DIR, zip_filename)
        try:
            shutil.make_archive(base_name=os.path.splitext(zip_path)[0], format='zip', root_dir=project_path)
            logger.info(f"Created ZIP file: {zip_path}")
        except Exception as e:
            flash(f'Error creating ZIP file: {e}', 'error')
            logger.error(f"Error creating ZIP file: {e}")
            shutil.rmtree(project_path)  # Remove the project directory on error
            return redirect(url_for('index'))
        
        # -------------------------------------
        # Remove the Project Directory After Zipping (Optional)
        # -------------------------------------
        shutil.rmtree(project_path)
        logger.info(f"Removed project directory: {project_path}")
        
        # -------------------------------------
        # Redirect to Download Page
        # -------------------------------------
        flash('Project generated successfully!', 'success')
        return redirect(url_for('download', filename=zip_filename))
    
    # Render the main page with the form
    return render_template('index.html')

# ------------------------------
# Route: Download Generated Project
# ------------------------------
@app.route('/download/<filename>')
def download(filename):
    try:
        logger.info(f"User requested download for: {filename}")
        return send_from_directory(BASE_DIR, filename, as_attachment=True)
    except FileNotFoundError:
        flash('File not found.', 'error')
        logger.error(f"File not found: {filename}")
        return redirect(url_for('index'))

# ------------------------------
# Run the Flask Application
# ------------------------------
if __name__ == '__main__':
    # IMPORTANT: In production, use a production-ready server like Gunicorn.
    # Do NOT use debug=True in production as it can expose sensitive information.
    app.run(debug=True)
