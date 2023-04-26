if (!dgenies.run) {
  throw "dgenies wasn't included!"
}
dgenies.run.batchParser = {};


/**
 * We use chevrotain
 *
 * See farther details here:
 * https://chevrotain.io/docs/guide/concrete_syntax_tree.html
 */

// ----------------- lexer -----------------
// using the NA pattern marks this Token class as 'irrelevant' for the Lexer.
// AdditionOperator defines a Tokens hierarchy but only the leafs in this hierarchy define
// actual Tokens that can appear in the text

dgenies.run.batchParser.Comment = chevrotain.createToken({ name: "Comment", pattern: /#[^\n\r]*/, group: chevrotain.Lexer.SKIPPED})

dgenies.run.batchParser.Affectation = chevrotain.createToken({ name: "Affectation", pattern: /=/ , push_mode: "value_mode" })

dgenies.run.batchParser.Value = chevrotain.createToken({ name: "Value", pattern: /[^#\s'"]+/, pop_mode: true })

dgenies.run.batchParser.DQuotedValue = chevrotain.createToken({ name: "DQuotedValue", pattern: /"[^"#\r\n]+"/, pop_mode: true })

dgenies.run.batchParser.SQuotedValue = chevrotain.createToken({ name: "SQuotedValue", pattern: /'[^'#\r\n]+'/, pop_mode: true })

dgenies.run.batchParser.Key = chevrotain.createToken({ name: "Key", pattern: /(type|align|query|target|backup|tool|options|id_job)/ })

dgenies.run.batchParser.NewLines = chevrotain.createToken({ name: "NewLines", pattern: /[\n\r]+/})

dgenies.run.batchParser.Spaces = chevrotain.createToken({ name: "Spaces", pattern: /[\t ]+/})

dgenies.run.batchParser.multiModeBatchLexerDefinition = {
  modes: {
    key_mode: [
      dgenies.run.batchParser.Comment,
      dgenies.run.batchParser.Key,
      dgenies.run.batchParser.Affectation,
      dgenies.run.batchParser.Spaces,
      dgenies.run.batchParser.NewLines
    ],
    value_mode: [
      dgenies.run.batchParser.Comment,
      dgenies.run.batchParser.DQuotedValue,
      dgenies.run.batchParser.SQuotedValue,
      dgenies.run.batchParser.Value,
      dgenies.run.batchParser.Spaces
    ]
  },
  defaultMode: "key_mode"
}

// Our new lexer now support 3 different modes
// To mode switching logic works by using a mode stack and pushing and popping modes.
// using the PUSH_MODE and POP_MODE static properties defined on the Token classes
dgenies.run.batchParser.MultiModeBatchLexer = new chevrotain.Lexer(dgenies.run.batchParser.multiModeBatchLexerDefinition)

class BatchParser extends chevrotain.CstParser {
  constructor() {
    super(dgenies.run.batchParser.multiModeBatchLexerDefinition)
        
    // Job alone or job followed by other jobs by using whitespaces with at least one newline as separator.
    // jobs:
    //    whiteSpaces job (spaces? newlines jobs)* whitespaces
    this.RULE("jobs", () => {
      this.SUBRULE(this.whiteSpaces);
      this.SUBRULE(this.job);
      this.MANY(() => {
        // manages whitespaces around mandatory newline separating jobs
        this.OPTION(() => {
            this.CONSUME(dgenies.run.batchParser.Spaces);
          }
        );
        this.CONSUME(dgenies.run.batchParser.NewLines);
        this.OPTION1(() => {
          this.SUBRULE1(this.job);
        });
      })
      // remove tailing whitespaces if exists
      this.SUBRULE2(this.whiteSpaces);
    })
    
    // Simulate \s*
    // whiteSpaces:
    //    (Spaces|NewLines)*
    this.RULE("whiteSpaces", () => {
      this.MANY(() => {
        this.OR([
          { ALT:() => { this.CONSUME(dgenies.run.batchParser.NewLines)}},
          { ALT:() => { this.CONSUME(dgenies.run.batchParser.Spaces)}}
        ])
      })
    })
    
  // job:
    //    param (Spaces param)* Spaces?
    this.RULE("job", () => {
      this.SUBRULE(this.param);
  this.MANY(() => {
          this.CONSUME1(dgenies.run.batchParser.Spaces)
          this.SUBRULE1(this.param);
        }
      );
      this.OPTION1(() => {
        // remove tailing spaces if exists
        this.CONSUME2(dgenies.run.batchParser.Spaces)
      })
    })

    //param: 
    //    Key Affectation value;
    this.RULE("param", () => {
      this.CONSUME(dgenies.run.batchParser.Key)
      this.CONSUME(dgenies.run.batchParser.Affectation)
      //this.CONSUME(Value)
      this.SUBRULE(this.value)
    })
    
    //value:
    //    DQuotedValue|SQuotedValue|Value
    this.RULE("value", () => {
      this.OR([
        { ALT:() => { this.CONSUME(dgenies.run.batchParser.DQuotedValue)}},
        { ALT:() => { this.CONSUME(dgenies.run.batchParser.SQuotedValue)}},
        { ALT:() => { this.CONSUME(dgenies.run.batchParser.Value) }}
      ])
    })

    this.performSelfAnalysis()
  }
}

// CST Visitor

dgenies.run.batchParser.parserInstance = new BatchParser([], { outputCst: true })

class BatchToAstVisitor extends dgenies.run.batchParser.parserInstance.getBaseCstVisitorConstructor() {
  constructor() {
    super()
    // The "validateVisitor" method is a helper utility which performs static analysis
    // to detect missing or redundant visitor methods
    this.validateVisitor()
  }


  // All Spaces, Newlines and whiteSpaces will be ignored 

  // jobs:
  //    whiteSpaces job (spaces? newlines jobs)* whitespaces
  jobs(ctx) {
    let jobs = []
    ctx.job.forEach((j) => {
      // there will be one operator for each rhs operand
      jobs.push(this.visit(j))
    })
    return jobs
  }


  whiteSpaces(ctx) {
    return undefined
  }

  
  //param
  //    : Key Affectation Value;
  param(ctx) {
    let key = {
      image: ctx.Key[0].image,
      startLine: ctx.Key[0].startLine,
      startColumn: ctx.Key[0].startColumn,
      endLine: ctx.Key[0].endLine,
      endColumn: ctx.Key[0].endColumn
    }
    let value = this.visit(ctx.value)
    return [key, value]
  }

  // job:
  //    param (Spaces param)* Spaces?
  job(ctx) {
    let params = []
    ctx.param.forEach((p) => {
      params.push(this.visit(p))
    })
    return params
  }



  //value:
  //    DQuotedValue|SQuotedValue|Value
  value(ctx) {
    let val;
    let ctxVal;
    if (ctx.Value) {
      ctxVal = ctx.Value[0]
      val = ctxVal.image
    }
    if (ctx.SQuotedValue) {
      ctxVal = ctx.SQuotedValue[0]
      val = ctxVal.image.substring(1, ctxVal.image.length-1)
    }
    if (ctx.DQuotedValue) {
      ctxVal = ctx.DQuotedValue[0]
      val = ctxVal.image.substring(1, ctxVal.image.length-1)
    }
    return {
      image: val,
      startLine: ctxVal.startLine,
      startColumn: ctxVal.startColumn,
      endLine: ctxVal.endLine,
      endColumn: ctxVal.endColumn
    }
  }


}


dgenies.run.batchParser.toAstVisitorInstance = new BatchToAstVisitor()

dgenies.run.batchParser.parse = function(inputText) {

  const parser = dgenies.run.batchParser.parserInstance
  // Lex
  const lexer = dgenies.run.batchParser.MultiModeBatchLexer.tokenize(inputText)
  parser.input = lexer.tokens

  // Automatic CST created when parsing
  const cst = parser.jobs()
  if (parser.errors.length > 0) {
    console.log(parser.errors)
/*    throw Error(
      "Parsing errors detected!\n" +
      parser.errors[0].token.startLine + ":" + 
      parser.errors[0].token.startOffset + " -> " + 
      parser.errors[0].token.endLine + ":" + 
        (parser.errors[0].token.startOffset + parser.errors[0].token.image.length) + "\n" +
        parser.errors[0].message
    )
    */
  }

  // Visit
  const data = dgenies.run.batchParser.toAstVisitorInstance.visit(cst)
  return {
    data : data !== undefined ? data : [],
    lexErrors: lexer.errors !== undefined ? lexer.errors : [],
    parseErrors: parser.errors !== undefined ? parser.errors : []
  }
}