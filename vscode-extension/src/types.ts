export type FileStatus = "queued" | "processing" | "done" | "error";

export interface PdfFile {
  id: string;
  name: string;
  relativePath: string;
  status: FileStatus;
  addedAt: string;
  completedAt?: string;
  errorMessage?: string;
}

export interface Session {
  id: string;
  name: string;
  createdAt: string;
  files: PdfFile[];
  isActive: boolean;
}

export interface SessionStore {
  sessions: Session[];
}
