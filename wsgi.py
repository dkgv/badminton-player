from app import create_app, is_production

app = create_app()
app.run(host="0.0.0.0", debug=not is_production)
