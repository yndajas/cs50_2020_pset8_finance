import os

from cs50 import SQL
from flask import Flask, flash, jsonify, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""

    # Get user's shares
    shares = db.execute("SELECT symbol, shares FROM shares WHERE user_id = :user_id", user_id = session["user_id"])

    # Create variable to store user's total worth
    total = 0

    # If there are any shares, for each share, get a new quote and add key/value pairs for the name and current value
    if shares:
        for symbol in shares:
            quote = lookup(symbol["symbol"])
            symbol["name"] = quote["name"]
            symbol["price"] = quote["price"]
            symbol["total"] = symbol["shares"] * symbol["price"]

            # add value of shares to user total
            total += symbol["total"]

    # Get user's cash
    cash = db.execute("SELECT cash FROM users WHERE id = :id", id = session["user_id"])[0]['cash']

    # Add cash to user's total worth
    total += cash

    return render_template("index.html", shares = shares, cash = cash, total = total)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure symbol was provided
        if not request.form.get("symbol"):
            return apology("must provide symbol", 403)

        # Ensure shares were provided
        new_shares = request.form.get("shares")

        if not new_shares:
            return apology("must provide number of shares", 403)

        # changed input type to number and min to 1 in the HTML, so this check is no longer needed
        # # Ensure integer was provided for shares
        # try:
        #     int(new_shares)
        # except ValueError:
        #     return apology("shares must be a whole number", 403)

        # Convert new_shares variable to integer type
        new_shares = int(new_shares)

        # changed input type to number and min to 1 in the HTML, so this check is no longer needed
        # # Ensure new_shares is greater than 0
        # if not new_shares > 0:
        #     return apology("shares must be greater than zero", 403)

        # Request quote
        symbol = request.form.get("symbol")

        quote = lookup(symbol)

        # Ensure quote has been retrieved
        if not quote:
            return apology("symbol not found", 403)

        # If quote has been received, get the price and calculate the total cost
        price = quote["price"]
        cost = new_shares * price

        # Ensure the user has sufficient funds to cover the cost
        cash = db.execute("SELECT cash FROM users WHERE id = :id", id = session["user_id"])[0]['cash']

        if cost > cash:
            return apology("insufficient funds", 403)

        # Get the canonincally formatted symbol (rather than the symbol as per user input, ensuring capitalisation) and name
        symbol = quote["symbol"]

        # Get existing shares in the company if there are any
        existing_shares = db.execute("SELECT id, shares FROM shares WHERE user_id = :user_id AND symbol = :symbol", user_id = session["user_id"], symbol = symbol)

        # If there are existing shares, add the new shares to the existing shares
        if existing_shares:
            db.execute("UPDATE shares SET shares = :shares WHERE id = :id", shares = existing_shares[0]['shares'] + new_shares, id = existing_shares[0]['id'])
        # Otherwise add them as a new row
        else:
            db.execute("INSERT INTO shares (user_id, symbol, shares) VALUES (:user_id, :symbol, :shares)", user_id = session["user_id"], symbol = symbol, shares = new_shares)

        # Update cash in users table
        db.execute("UPDATE users SET cash = :cash WHERE id = :id", cash = cash - cost, id = session["user_id"])

        # Log transaction in transactions table
        db.execute("INSERT INTO transactions (user_id, type, symbol, shares, price) VALUES (:user_id, 'Bought', :symbol, :shares, :price)", user_id = session["user_id"], symbol = symbol, shares = new_shares, price = price)

        # Create flash message to be displayed on next page then redirect
        flash('Bought!')
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""

    # Get user's transactions
    transactions = db.execute("SELECT type, symbol, shares, price, date FROM transactions WHERE user_id = :user_id", user_id = session["user_id"])

    return render_template("history.html", transactions = transactions)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure symbol was provided
        if not request.form.get("symbol"):
            return apology("must provide symbol", 403)

        # Request quote
        symbol = request.form.get("symbol")

        quote = lookup(symbol)

        # Ensure quote has been retrieved
        if not quote:
            return apology("symbol not found", 403)

        # If quote was retrieved
        else:
            return render_template("quoted.html", quote = quote)

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Ensure password was submitted
        elif not request.form.get("confirmation"):
            return apology("must provide password confirmation", 403)

        # Ensure passwords match
        elif not request.form.get("password") == request.form.get("confirmation"):
            return apology("passwords do not match", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        # Ensure username does not exist
        if len(rows) > 0:
            return apology("username already exists", 403)

        # Add user to users table
        else:
            username = request.form.get("username")
            hash = generate_password_hash(request.form.get("username"))
            db.execute("INSERT INTO users (username, hash) VALUES (:username, :hash)", username = username, hash = hash)

            # Remember which user has logged in
            session["user_id"] = db.execute("SELECT id FROM users WHERE username = :username", username = username)[0]["id"]

            # Create flash message to be displayed on next page then redirect user to home page
            flash('Registered!')
            return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure symbol was provided
        if not request.form.get("symbol"):
            return apology("must provide symbol", 403)

        # Ensure shares were provided
        shares = request.form.get("shares")

        if not shares:
            return apology("must provide number of shares", 403)

        # Convert shares variable to integer type and save symbol as variable
        shares = int(shares)
        symbol = request.form.get("symbol")

        # Ensure user has enough shares to sell
        existing_shares = db.execute("SELECT shares FROM shares WHERE user_id = :user_id AND symbol = :symbol", user_id = session["user_id"], symbol = symbol)[0]['shares']

        if shares > existing_shares:
            return apology("insufficient shares to sell", 403)

        # Request quote
        quote = lookup(symbol)

        # Ensure quote has been retrieved
        if not quote:
            return apology("symbol not found", 403)

        # If quote has been received, get the price and calculate the total value of the sale and the remaining shares after sale
        price = quote["price"]
        value = shares * price
        remaining_shares = existing_shares - shares

        # Delete entry in shares table if there will be no shares remaining
        if remaining_shares == 0:
            db.execute("DELETE FROM shares WHERE user_id = :user_id AND symbol = :symbol", user_id = session["user_id"], symbol = symbol)

        # Update shares in shares table if there will be some remaining shares
        else:
            db.execute("UPDATE shares SET shares = :remaining_shares WHERE user_id = :user_id AND symbol = :symbol", user_id = session["user_id"], symbol = symbol, remaining_shares = remaining_shares)

        # Get user's existing cash
        cash = db.execute("SELECT cash FROM users WHERE id = :id", id = session["user_id"])[0]['cash']

        # Update cash in users table
        db.execute("UPDATE users SET cash = :cash WHERE id = :id", cash = cash + value, id = session["user_id"])

        # Log transaction in transactions table
        db.execute("INSERT INTO transactions (user_id, type, symbol, shares, price) VALUES (:user_id, 'Sold', :symbol, :shares, :price)", user_id = session["user_id"], symbol = symbol, shares = shares, price = price)

        # Create flash message to be displayed on next page then redirect
        flash('Sold!')
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        # get symbols of user's shares
        symbols = db.execute("SELECT symbol FROM shares WHERE user_id = :user_id", user_id = session["user_id"])
        return render_template("sell.html", symbols = symbols)


@app.route("/change-username", methods=["GET", "POST"])
@login_required
def change_username():
    """Show history of transactions"""

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        # Ensure old username was submitted
        if not request.form.get("old-username"):
            return apology("must provide old username", 403)

        # Ensure new username was submitted
        if not request.form.get("new-username"):
            return apology("must provide new username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Save variables from form
        old_username = request.form.get("old-username")
        new_username = request.form.get("new-username")
        password = request.form.get("password")

        # Query database for old username
        user_data = db.execute("SELECT * FROM users WHERE username = :old_username",
                          old_username=old_username)

        # Ensure old username exists and password is correct
        if len(user_data) != 1 or not check_password_hash(user_data[0]["hash"], password):
            return apology("invalid (old) username and/or password", 403)

        # Query database for new username
        new_username_in_db = db.execute("SELECT * FROM users WHERE username = :new_username",
                          new_username=new_username)

        # Ensure new username does not exist
        if len(new_username_in_db) > 0:
            return apology("requested username already exists", 403)

        # All being well, chaneg username
        else:
            db.execute("UPDATE users SET username = :new_username WHERE username = :old_username", new_username = new_username, old_username = old_username)

        # Flash success message and return to index
        flash('Username successfully updated!')
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("change-username.html")


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
