require('dotenv').config();

const heimdall = require('@ctrlb/heimdall');

heimdall.start({
  apiKey: "bla",
  brokerPort: "8094",
  brokerHost: "ws://localhost",
  applicationName: process.argv[2] || 8000,
  maxProperties: 20,
  maxDepth: 2,
});

const WebSocket = require('ws');
var express = require('express');
var path = require('path');
const fs = require('fs');
var bodyParser = require('body-parser');
var cookieParser = require('cookie-parser');
var api = require('./Routes/api');
const cors = require('cors'); // Import the cors middleware

var app = express();
app.use(cors()); // Enable CORS for all routes

app.set('port', (process.argv[2] || 8000));

var server = app.listen(app.get('port'), function () {
  console.log('listening on port ', app.get('port'));
  console.log("vtgrf");
});

app.use(bodyParser.urlencoded({ extended: true }));

app.use(cookieParser());

app.use(bodyParser.json());

app.use('/api', (req, res, next) => {
  res.header('Access-Control-Allow-Origin', '*');
  res.header('Access-Control-Allow-Method', 'GET, POST, HEAD, OPTIONS, PUT');
  res.header('Access-Control-Allow-Headers', 'Origin, Content-Type, Authorization');
  next();
});

app.use('/api', api);

// Add a route to serve the contents of api.js
app.get('/api/js', (req, res) => {
  const apiJSFilePath = path.join(__dirname, '../Server/Routes/api.js');
  fs.readFile(apiJSFilePath, 'utf8', (err, data) => {
    if (err) {
      console.error('Error reading api.js:', err);
      return res.status(500).send('Internal Server Error');
    }
    res.setHeader('Content-Type', 'application/javascript');
    res.send(data);
  });
});

// Initialize an array to store tracepoint events
const tracepointEventsByPort = {};
// const liveMessagesByPort = {}; // New object to store live messages

// Endpoint to add a tracepoint event
app.post('/addTracepointEvent', (req, res) => {

  const data = req.body;
  const port = data.port; // Extract port information from the data
  const liveMessage = data.live_message; // Extract live_message from the data
  // console.log(liveMessage, port)
  // Create an array for the port if not exists and push the live_message
  if (!tracepointEventsByPort[port]) {
    tracepointEventsByPort[port] = [];
  }
  tracepointEventsByPort[port].unshift(liveMessage);
  try {
    res.status(200).json({ message: 'Live message added successfully.' });
  } catch (error) {
    console.error('Error sending response:', error);
  }
});

// Endpoint to get tracepoint events for a specific port
app.get('/getTracepointEvents/:port', (req, res) => {
  const port = req.params.port;
  const events = tracepointEventsByPort[port] ;
  res.status(200).json({ events: events});
});

app.get('/ping', (req, res) => {
  res.send('pong');
});

app.all('*', function (req, res) {
  res.status(404).send('Nothing Here');
});

module.exports = server;