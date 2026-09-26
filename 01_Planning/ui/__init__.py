"""AZRAS Platform shared UI components."""

from .global_treeview import install_global_treeview

# Install before application windows are constructed. Existing module source can
# continue to call ttk.Treeview without individual rewrites.
install_global_treeview()

__all__ = ["install_global_treeview"]
