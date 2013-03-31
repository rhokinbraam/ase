class HomeController < ApplicationController
  def index
  end
  
  def student
      checkIfLoggedIn!
      @student = session[:username]   
      @assignment = Assignment.current_assignment
      @form_from_state = 'list'
      if(@assignment != nil) then
          case @assignment.state
             when "BUSY"
                 @essay = @assignment.essays.where(:studentname => @student).first
                 if @essay == nil 
                     @essay = @assignment.essays.new
                 end    
                 @form_from_state = 'enter'
             when "MARKING"
                 evals = EssayEval.where(:studentname => @student)
                 @mark_index = params[:mark_index]+1 rescue 0
                 if @mark_index >= evals.length 
                     @mark_index = 0
                 end    
                 @essayeval = evals[@mark_index]
                 @score = @essayeval.score1.nil? ? 0.5 : @essayeval.score1
                 @essay1 = Essay.find(@essayeval.essay1_id)
                 @essay2 = Essay.find(@essayeval.essay2_id)                 
                 @form_from_state = 'mark'         
          end   
      end
  end
  
  def save
    checkIfLoggedIn!
    @essay = Essay.find(params[:id]) rescue Essay.new
    @essay.studentname = session[:username]
    @essay.update_attributes(params[:essay])

    redirect_to student_url, notice: 'Essay saved.' 
  end
  
  def score
    checkIfLoggedIn!
    evals = EssayEval.find(params[:id])
    evals.score1 = params[:scorerange].to_f
    evals.score2 = 1-evals.score1
    evals.save
    redirect_to student_url(:mark_index => params[:mark_index]), notice: 'Essay saved.' 
  end
    
  def login 
      if params[:username] then
          session[:username] = params[:username]
          redirect_to student_url
      end    
  end
  
  def logout 
      session.delete :username
      redirect_to login_url      
  end
  
  
  def checkIfLoggedIn!
      if session.has_key? :username then
           return true
      else
           redirect_to login_url
      end
  end
  
end
