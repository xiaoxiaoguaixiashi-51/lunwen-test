"""Offline source-context baselines, not a production generator or new research algorithm."""
import hashlib
from pathlib import Path
import javalang
from src.utils.focal_target import select_method, parameter_types


def offset(source, position):
    return sum(len(line) for line in source.splitlines(keepends=True)[:position.line-1]) + position.column-1


def node_source(source, tokens, node):
    """Keep an entire declaration; strings/comments do not act as braces."""
    positions = [node.position,*[item.position for item in getattr(node,'annotations',[]) if item.position]]
    start_position=min(positions)
    index=next(i for i,token in enumerate(tokens) if token.position>=start_position)
    while index>0 and tokens[index-1].value in javalang.tokenizer.Modifier.VALUES:
        index-=1
    start_position=tokens[index].position
    start=offset(source,start_position)
    selected = (token for token in tokens if token.position>=start_position)
    parens = braces = 0
    in_body = False
    for token in selected:
        value=token.value
        if isinstance(token,(javalang.tokenizer.String,javalang.tokenizer.Character)):
            continue
        if value=='(':
            parens+=1
        elif value==')':
            parens-=1
        elif value=='{' and (in_body or parens==0):
            in_body=True
            braces+=1
        elif value=='}' and in_body:
            braces-=1
            if braces==0:
                end=offset(source,token.position)+1
                return source[start:end]
        elif value==';' and not in_body and parens==0:
            return source[start:offset(source,token.position)+1]
    raise ValueError('Unterminated source declaration')


def ast_shape(value):
    if isinstance(value,javalang.ast.Node):
        return (type(value).__name__,tuple((name,ast_shape(getattr(value,name)))
                for name in value.attrs if name!='documentation'))
    if isinstance(value,list):
        return tuple(ast_shape(item) for item in value)
    if isinstance(value,set):
        return tuple(sorted(value))
    return value


def declaration_header(text):
    parens=0
    for token in javalang.tokenizer.tokenize(text):
        if isinstance(token,(javalang.tokenizer.String,javalang.tokenizer.Character)):
            continue
        if token.value=='(':
            parens+=1
        elif token.value==')':
            parens-=1
        elif token.value=='{' and parens==0:
            return text[:offset(text,token.position)].strip()
    return text.strip().removesuffix(';')


def context_parts(method):
    path=Path(method['target'])
    content=path.read_bytes()
    if hashlib.sha256(content).hexdigest()!=method['source_sha256']:
        raise ValueError('Frozen source hash changed')
    source=content.decode('utf-8')
    tree=javalang.parse.parse(source)
    owner,focal=select_method(tree,method['method'],method['method_owner'],method['method_parameter_types'])
    tokens=list(javalang.tokenizer.tokenize(source))
    header=('package '+tree.package.name+';\n') if tree.package else ''
    header+='\n'.join('import '+('static ' if imp.static else '')+imp.path+('.*' if imp.wildcard else '')+';' for imp in tree.imports)
    declaration=declaration_header(node_source(source,tokens,owner))
    declarations=[]
    for field in owner.fields:
        type_node=field.type
        type_names=[type_node.name]
        while getattr(type_node,'sub_type',None) is not None:
            type_node=type_node.sub_type
            type_names.append(type_node.name)
        typename='.'.join(type_names)+'[]'*len(field.type.dimensions or [])
        declarations.append(' '.join(sorted(field.modifiers))+' '+typename+' '+', '.join(d.name for d in field.declarators)+';')
    for constructor in owner.constructors:
        declarations.append(declaration_header(node_source(source,tokens,constructor))+';')
    focal_text=node_source(source,tokens,focal)
    reparsed=javalang.parse.parse('class Context {\n'+focal_text+'\n}').types[0].methods
    if len(reparsed)!=1 or ast_shape(reparsed[0])!=ast_shape(focal):
        raise ValueError('Extracted focal declaration does not round-trip to the original AST')
    mandatory=('PARTIAL SOURCE CONTEXT; this is not a complete compilation unit. Missing code is unknown, not absent.\n'
        'Field types below are erased declarations; initializers are omitted. Constructor headers omit bodies. Javadoc is omitted.\n'
        +header+'\nDeclaring type header:\n'+declaration+'\nPartial fields and constructor declarations:\n'
        +'\n'.join(declarations)+'\nExact focal declaration '+method['method_owner']+'.'+method['method']
        +str(method['method_parameter_types'])+':\n'+focal_text)
    local=[]
    calls={call.member for path,call in focal.filter(javalang.tree.MethodInvocation)
           if (not call.qualifier or call.qualifier in {'this',owner.name})
           and not any(isinstance(node,(javalang.tree.ClassCreator,javalang.tree.TypeDeclaration)) for node in path)}
    for helper in owner.methods:
        if helper is focal or helper.name not in calls:
            continue
        # Include all local overload candidates; no claim of full type resolution.
        local.append({'name':helper.name,'parameter_types':parameter_types(helper),
            'start_line':helper.position.line,'text':node_source(source,tokens,helper)})
    return {'mandatory':mandatory,'focal_text':focal_text,'local_helper_candidates':local,
            'focal_sha256':hashlib.sha256(focal_text.encode()).hexdigest(),
            'source_sha256':method['source_sha256'],'source_file':str(path)}


def build_context(method, fits):
    parts=context_parts(method)
    baseline=parts['mandatory']
    expanded=baseline
    included=[]
    excluded=[]
    for helper in parts['local_helper_candidates']:
        candidate=expanded+'\nSame-type direct-name callee candidate (overload resolution unknown):\n'+helper['text']
        target=included if fits(candidate) else excluded
        target.append({key:value for key,value in helper.items() if key!='text'})
        if target is included:
            expanded=candidate
    return {'F1':baseline,'F2':expanded,'mandatory_fits':bool(fits(baseline)),
            'focal_sha256':parts['focal_sha256'],'source_sha256':parts['source_sha256'],
            'included_local_helpers':included,'excluded_local_helpers':excluded,
            'limits':['Focal body is never truncated or replaced by another overload.',
                      'No dependency traversal, complete call graph, constructor execution or test-generation claim.',
                      'No project tests, generated tests or evaluation answers included.',
                      'F2 only adds same-declaring-type direct-name candidates; missing external guards remain unknown.']}
