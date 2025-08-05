import React, { memo } from 'react';

interface MarkdownComponentProps {
  children?: React.ReactNode;
  [key: string]: unknown;
}

const TableContainerComponent: React.FC<MarkdownComponentProps> = ({ children, ...props }) => (
  <div className="table-container">
    <table className="markdown-table" {...props}>{children}</table>
  </div>
);

const TableHeaderComponent: React.FC<MarkdownComponentProps> = ({ children, ...props }) => (
  <thead className="table-header" {...props}>{children}</thead>
);

const TableBodyComponent: React.FC<MarkdownComponentProps> = ({ children, ...props }) => (
  <tbody className="table-body" {...props}>{children}</tbody>
);

const TableRowComponent: React.FC<MarkdownComponentProps> = ({ children, ...props }) => (
  <tr className="table-row" {...props}>{children}</tr>
);

const TableHeaderCellComponent: React.FC<MarkdownComponentProps> = ({ children, ...props }) => (
  <th className="table-header-cell" {...props}>{children}</th>
);

const TableCellComponent: React.FC<MarkdownComponentProps> = ({ children, ...props }) => (
  <td className="table-cell" {...props}>{children}</td>
);

export const TableContainer = memo(TableContainerComponent);
export const TableHeader = memo(TableHeaderComponent);
export const TableBody = memo(TableBodyComponent);
export const TableRow = memo(TableRowComponent);
export const TableHeaderCell = memo(TableHeaderCellComponent);
export const TableCell = memo(TableCellComponent); 