This is a Flask application for a website for ice hockey or football predictions, based on this [blog](https://blog.miguelgrinberg.com/post/the-flask-mega-tutorial-part-i-hello-world)

- [HTML basics](https://en.wikipedia.org/wiki/HTML#Markup)

- Deployed with [Render](https://dashboard.render.com/)

- Tickets on [Clickup](https://app.clickup.com/9004043647/v/b/4-90040090140-2)

- [Readme markups](https://docs.github.com/en/get-started/writing-on-github/getting-started-with-writing-and-formatting-on-github/basic-writing-and-formatting-syntax)

### To run it on dev

To switch between the ice hockey and football modes, go to _config.py_ file and change the **SPORT** variable accordingly.

While in the top directory and using an Ubuntu (wsl) terminal on VSCode, first install venv (if this is the first time you run it) ````python3 -m venv venv````, then activate it with ````source venv/bin/activate```` and install the requirements ````pip install -r requirements.txt```` (needed only the first time). Finally, just run ````flask run````.

### Initial user setup

To create the main/first admin user, after registering through the website, you have to manually set is_admin=True in the db for the user you want to be an admin. After that, it#s posible to add and remove admins through the website.