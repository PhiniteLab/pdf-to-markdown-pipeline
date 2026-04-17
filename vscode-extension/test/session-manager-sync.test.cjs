const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const Module = require('node:module');

class EventEmitter {
  constructor() {
    this.listeners = new Set();
    this.event = (listener) => {
      this.listeners.add(listener);
      return { dispose: () => this.listeners.delete(listener) };
    };
  }
  fire(value) {
    for (const listener of this.listeners) {
      listener(value);
    }
  }
  dispose() {
    this.listeners.clear();
  }
}

const originalLoad = Module._load;
Module._load = function patchedLoad(request, parent, isMain) {
  if (request === 'vscode') {
    return { EventEmitter };
  }
  return originalLoad(request, parent, isMain);
};

const { SessionManager } = require('../out/sessionManager.js');

function makePolicy(workspaceRoot) {
  const sessionsRoot = path.join(workspaceRoot, 'sessions');
  return {
    workspaceRoot,
    configPath: path.join(workspaceRoot, 'configs', 'pipeline.yaml'),
    configDir: path.join(workspaceRoot, 'configs'),
    configFound: false,
    configNotes: [],
    dataRoot: path.join(workspaceRoot, 'data', 'raw'),
    sessionsRoot,
    outputRoots: {
      rawMd: path.join(workspaceRoot, 'outputs', 'raw_md'),
      cleanedMd: path.join(workspaceRoot, 'outputs', 'cleaned_md'),
      chunks: path.join(workspaceRoot, 'outputs', 'chunks'),
      quality: path.join(workspaceRoot, 'outputs', 'quality'),
      semanticChunks: path.join(workspaceRoot, 'outputs', 'semantic_chunks'),
    },
    manifestPath: path.join(workspaceRoot, 'outputs', '.manifest.json'),
    sessionStorePath: path.join(workspaceRoot, '.cortexmark', 'sessions.json'),
    legacySessionStorePath: path.join(workspaceRoot, '.phinitelab-pdf-pipeline', 'sessions.json'),
    sessionOutputs(sessionName) {
      const safe = sessionName;
      const sessionRoot = path.join(sessionsRoot, safe);
      const dataDir = path.join(sessionRoot, 'data');
      const inputDir = path.join(dataDir, 'raw');
      const outputsDir = path.join(sessionRoot, 'outputs');
      const qualityDir = path.join(outputsDir, 'quality');
      return {
        sessionRoot,
        dataDir,
        inputDir,
        outputsDir,
        rawDir: path.join(outputsDir, 'raw_md'),
        cleanedDir: path.join(outputsDir, 'cleaned_md'),
        chunksDir: path.join(outputsDir, 'chunks'),
        qualityDir,
        semanticDir: path.join(outputsDir, 'semantic_chunks'),
        manifestPath: path.join(outputsDir, '.manifest.json'),
        reportPath(fileName) {
          return path.join(qualityDir, fileName);
        },
      };
    },
  };
}

test('syncSessionInputFolder discovers PDFs copied manually into the session input dir', () => {
  const workspaceRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'cortexmark-session-sync-'));
  const mgr = new SessionManager(makePolicy(workspaceRoot));
  const session = mgr.create('manual-drop');
  const inputDir = mgr.pathsFor(session).inputDir;
  const nestedDir = path.join(inputDir, 'batch-1');
  fs.mkdirSync(nestedDir, { recursive: true });
  fs.writeFileSync(path.join(nestedDir, 'paper-a.pdf'), 'pdf-a');
  fs.writeFileSync(path.join(nestedDir, 'paper-b.PDF'), 'pdf-b');

  const added = mgr.syncSessionInputFolder(session.id);
  const refreshed = mgr.get(session.id);

  assert.equal(added, 2);
  assert.ok(refreshed);
  assert.equal(refreshed.files.length, 2);
  assert.deepEqual(
    refreshed.files.map((file) => file.name).sort(),
    ['paper-a.pdf', 'paper-b.PDF'],
  );
  assert.ok(refreshed.files.every((file) => file.status === 'queued'));
});
