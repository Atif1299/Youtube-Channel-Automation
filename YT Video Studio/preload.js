const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("api", {
  checkEnv: () => ipcRenderer.invoke("env:check"),
  
  listNiches: () => ipcRenderer.invoke("niche:list"),
  
  fetchTrending: (opts) => ipcRenderer.invoke("research:trending", opts || {}),
  
  generateScript: (opts) => ipcRenderer.invoke("script:generate", opts),
  
  createJob: (opts) => ipcRenderer.invoke("job:create", opts),
  startJob: (jobId) => ipcRenderer.invoke("job:start", { jobId }),
  getJobStatus: (jobId) => ipcRenderer.invoke("job:status", { jobId }),
  listJobs: () => ipcRenderer.invoke("job:list"),
  cancelJob: (jobId) => ipcRenderer.invoke("job:cancel", { jobId }),
  deleteJob: (jobId) => ipcRenderer.invoke("job:delete", { jobId }),
  
  approveVideo: (jobId) => ipcRenderer.invoke("video:approve", { jobId }),
  rejectVideo: (jobId) => ipcRenderer.invoke("video:reject", { jobId }),
  getVideoUrl: (jobId) => ipcRenderer.invoke("video:url", { jobId }),
  
  getYouTubeStatus: () => ipcRenderer.invoke("youtube:status"),
  startYouTubeAuth: () => ipcRenderer.invoke("youtube:auth"),
  publishVideo: (jobId, publishAt) => ipcRenderer.invoke("youtube:publish", { jobId, publishAt }),
  
  generateDirect: (opts) => ipcRenderer.invoke("generate:direct", opts),
});
