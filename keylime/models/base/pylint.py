"""
Pylint/Astroid plugin to suppress overzealous error/warnings which arise when writing model definitions as a result
of the meta-programming features used to implement the schema domain-specific language (DSL). Because they are 
appropriate and expected in other areas of the codebase, we cannot simply disable the relevant errors/warnings.
Instead, this plugin targets models specifically and modifies the in-memory Astroid representation of their source code
to eliminate the conditions which produce the errors/warnings prior to consumption by Pylint.
"""

import os
from typing import TYPE_CHECKING

import astroid

if TYPE_CHECKING:
    from pylint.lint import PyLinter

# Methods in BasicModel and PersistableModel which dynamically transform the model at runtime by adding members
# (e.g., ``self._field("name")`` creates a new property to allow the field to be accessed with ``model.name``)
MODEL_TRANSFORMING_METHODS = ["_field", "_id", "_has_one", "_has_many", "_belongs_to"]

# List of all DSL constructs exported by keylime.model.base, to be populated on plugin registration
base_exports: list[str] = []


def register(_linter: "PyLinter") -> None:
    """Obtains the exports of the ``keylime.model.base`` package by parsing ``keylime/model/base/__init__.py`` into
    an abstract syntax tree (AST) and iterating through the ``import`` statements contained within. Called by Pylint
    on plugin registration.
    """
    if base_exports:
        return

    path = os.path.dirname(os.path.realpath(__file__))
    path = os.path.join(path, "__init__.py")

    with open(path, encoding="utf-8") as f:
        init_contents = f.read()

    init_mod = astroid.parse(init_contents)

    if not init_mod.body:
        return

    for item in init_mod.body:
        if isinstance(item, astroid.ImportFrom):
            for name in item.names:
                base_exports.append(name[1] or name[0])


def transform_model_class(cls: astroid.ClassDef) -> astroid.ClassDef:
    """Given the Astroid abstract syntax tree (AST) of a model class, modifies it to include those members which are not
    present in the source code but created dynamically at runtime. This is achieved by inspecting the schema definition
    of the model and identifying calls which trigger creation of new fields or associations. Fake attributes are added
    to the AST for each field and association identified.

    This has the effect of suppressing "access-member-before-definition" (E0203) and
    "attribute-defined-outside-init" (W0201) when accessing a field or association using dot notation.
    """
    if (
        isinstance(cls.parent, astroid.Module)
        and cls.name
        and cls.parent.name
        and cls.parent.name.startswith("keylime.models")
        and not cls.parent.name.startswith("keylime.models.base")
    ):
        # Iterate over declarations in the body of the model's _schema method
        for exp in cls.locals["_schema"][0].body:
            # Only declarations which create a new field or association are relevant
            if exp.value.func.attrname in MODEL_TRANSFORMING_METHODS:
                # Get the first argument of the function call as this is the name of the field/association
                attr = exp.value.args[0].value
                # Add an attribute for the field/association to the AST
                cls.locals[attr] = [
                    astroid.FunctionDef(
                        attr, lineno=None, col_offset=None, parent=cls, end_lineno=None, end_col_offset=None
                    )
                ]

    return cls


def transform_model_module(mod: astroid.Module) -> astroid.Module:
    """Given the Astroid abstract syntax tree (AST) of a module containing a model, modifies it to replace any wildcard
    import of the ``keylime.models.base`` package with an explicit import that mentions all the items exported by the
    package by name. This is useful as defining a model consistently requires a good many constructs from
    ``keylime.models.base`` and so the model API has been designed to allow wildcard imports instead of tediously
    importing each construct manually.

    Additionally, a dummy function is added to the end of the module AST which references all the items imported from
    ``keylime.models.base``. This is so that if an available construct is not used in the model, this does not cause a
    further warning to be generated by Pylint.

    This has the effect of suppressing "wildcard-import" (W0401) and "unused-import" (W0611) when importing the model
    API in the prescribed manner.
    """
    if not mod.body:
        return mod

    # Return modules which are not expected to contain a model definition unchanged
    if (
        not mod.name
        or not mod.name.startswith("keylime.models")
        or mod.name.startswith("keylime.models.base")
        or "__init__" in mod.name
    ):
        return mod

    body = mod.body.copy()
    base_pkg = "keylime.models.base"

    # Iterate over statements in the module body
    for i, item in enumerate(body):
        # Only process the statement if it is a wildcard import of "keylime.models.base"
        if isinstance(item, astroid.ImportFrom) and item.modname == base_pkg and item.names == [("*", None)]:
            # From the list of base imports produced by the ``register(...)`` function, generate a list of import names
            # without any aliases (specifying None)
            import_names = [(name, None) for name in base_exports]  # type: list[tuple[str, str | None]]
            # Replace the wildcard import statement with a new import statement with all imports explicitly named
            body[i] = astroid.ImportFrom(base_pkg, import_names, item.level, item.lineno, item.col_offset, item.parent)

            # Create new dummy function to reference the imports and avoid "unused-import" warnings
            fake_f_code = f"def fake_import_use():\n" f"    return [{', '.join(base_exports)}]"

            # Get AST from dummy function and append it to the end of the statement tree
            fake_f = astroid.extract_node(fake_f_code, mod.name)
            body.append(fake_f)
            # Update module AST with altered statement tree
            mod.postinit(body)

            # Once a wildcard import of "keylime.models.base" is found, we can skip searching the rest of the tree
            break

    return mod


astroid.MANAGER.register_transform(astroid.ClassDef, transform_model_class)
astroid.MANAGER.register_transform(astroid.Module, transform_model_module)
