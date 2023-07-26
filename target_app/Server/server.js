var express = require('express');
var path = require('path');
var bodyParser = require('body-parser');
var cookieParser = require('cookie-parser');
var api = require('./Routes/api');

var app = express();

app.set('port', (process.argv[2] || 8000));

var server = app.listen(app.get('port'), function() {
  console.log('listening on port ',app.get('port'));
});

app.use(bodyParser.urlencoded({ extended: true }));
app.use(express.static(path.join(__dirname,'../../templates')));

app.use(cookieParser());

app.use(bodyParser.json());

app.use('/api', (req, res, next) => {
  res.header('Access-Control-Allow-Origin', '*');
  res.header('Access-Control-Allow-Method', 'GET, POST, HEAD, OPTIONS, PUT');
  res.header('Access-Control-Allow-Headers', 'Origin, Content-Type, Authorization');
  next();
});

app.use('/api', api);

app.get('/', function (req, res) {
	//res.status(200).send('Hi. Tic Tac Toe Homepage');
  res.sendFile(path.join(__dirname,'../../templates','tic-tac-toe.html'));
});

app.all('*', function (req, res) {
  res.status(404).send('Nothing Here');
});

module.exports = server;